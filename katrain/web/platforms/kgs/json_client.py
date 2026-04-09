"""KGS JSON protocol client.

HTTP long-polling client for the KGS Go server.
POST to send messages, GET to receive. Session maintained via cookies.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Callable, Optional

import httpx

logger = logging.getLogger("katrain_web")

KGS_URL = "https://www.gokgs.com/json/access"


class KGSJsonClient:
    """HTTP long-polling client for KGS JSON protocol."""

    def __init__(self, base_url: str = KGS_URL):
        self._base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None
        self._connected = False
        self._poll_task: Optional[asyncio.Task] = None
        self._callbacks: dict[str, list[Callable]] = defaultdict(list)
        self._username: Optional[str] = None
        self._user_rank: Optional[str] = None
        self._channels: dict[int, dict] = {}  # channelId -> channel info

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(65.0, connect=10.0),  # GET polls timeout at 60s
                follow_redirects=True,
                headers={
                    "User-Agent": "KaTrain-SmartBoard/0.1",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        self._connected = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    # --- Event registration ---

    def on(self, msg_type: str, handler: Callable) -> None:
        """Register a callback for a KGS message type."""
        self._callbacks[msg_type].append(handler)

    async def _dispatch(self, msg: dict) -> None:
        msg_type = msg.get("type", "")
        for cb in self._callbacks.get(msg_type, []):
            try:
                result = cb(msg)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Error in KGS callback for {msg_type}: {e}")

    # --- Connection lifecycle ---

    async def login(self, name: str, password: str) -> bool:
        """Authenticate with KGS. Starts the poll loop on success."""
        await self._send({"type": "LOGIN", "name": name, "password": password, "locale": "en_US"})

        # Start poll loop to receive LOGIN_SUCCESS
        self._connected = True
        self._poll_task = asyncio.create_task(self._poll_loop())

        # Wait briefly for LOGIN_SUCCESS
        login_success = asyncio.Event()
        login_failed = asyncio.Event()

        async def on_success(msg):
            self._username = msg.get("you", {}).get("name")
            self._user_rank = msg.get("you", {}).get("rank")
            login_success.set()

        async def on_failure(msg):
            login_failed.set()

        self.on("LOGIN_SUCCESS", on_success)
        self.on("LOGIN_FAILED_NO_SUCH_USER", on_failure)
        self.on("LOGIN_FAILED_BAD_PASSWORD", on_failure)
        self.on("LOGIN_FAILED_USER_ALREADY_EXISTS", on_failure)

        try:
            done, _ = await asyncio.wait(
                [asyncio.create_task(login_success.wait()), asyncio.create_task(login_failed.wait())],
                timeout=15.0,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if login_success.is_set():
                logger.info(f"KGS login successful: {self._username} ({self._user_rank})")
                return True
            else:
                logger.warning("KGS login failed")
                self._connected = False
                return False
        except asyncio.TimeoutError:
            logger.warning("KGS login timed out")
            self._connected = False
            return False

    async def logout(self) -> None:
        await self._send({"type": "LOGOUT"})
        await self.close()

    # --- Send / receive ---

    async def _send(self, message: dict) -> None:
        """POST a message to KGS."""
        client = await self._ensure_client()
        try:
            resp = await client.post(self._base_url, json=message)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"KGS send error: {e}")
            raise

    async def _poll_once(self) -> list[dict]:
        """GET pending messages from KGS. Blocks up to 60s."""
        client = await self._ensure_client()
        try:
            resp = await client.get(self._base_url)
            resp.raise_for_status()
            data = resp.json()
            return data.get("messages", [])
        except httpx.TimeoutException:
            # Normal — 60s poll timeout, no messages
            return []
        except Exception as e:
            logger.error(f"KGS poll error: {e}")
            return []

    async def _poll_loop(self) -> None:
        """Continuous poll loop — always have one GET pending."""
        retry_count = 0
        while self._connected:
            try:
                messages = await self._poll_once()
                retry_count = 0
                for msg in messages:
                    await self._dispatch(msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                retry_count += 1
                if retry_count > 10:
                    logger.error("KGS poll loop: too many retries, disconnecting")
                    self._connected = False
                    break
                await asyncio.sleep(min(3.0 * retry_count, 30.0))

    # --- Game actions ---

    async def join_channel(self, channel_id: int) -> None:
        """Join a room or game channel."""
        await self._send({"type": "JOIN_REQUEST", "channelId": channel_id})

    async def leave_channel(self, channel_id: int) -> None:
        await self._send({"type": "UNJOIN_REQUEST", "channelId": channel_id})

    async def game_move(self, channel_id: int, x: int, y: int) -> None:
        """Submit a move (0-indexed from top-left)."""
        await self._send({"type": "GAME_MOVE", "channelId": channel_id, "loc": {"x": x, "y": y}})

    async def game_pass(self, channel_id: int) -> None:
        await self._send({"type": "GAME_MOVE", "channelId": channel_id, "loc": "PASS"})

    async def game_resign(self, channel_id: int) -> None:
        await self._send({"type": "GAME_RESIGN", "channelId": channel_id})

    async def game_undo_request(self, channel_id: int) -> None:
        await self._send({"type": "GAME_UNDO_REQUEST", "channelId": channel_id})

    # --- Challenge ---

    async def challenge_create(self, room_channel_id: int, proposal: dict, global_challenge: bool = True) -> None:
        """Create a challenge in a room."""
        await self._send({
            "type": "CHALLENGE_CREATE",
            "channelId": room_channel_id,
            "callbackKey": 0,
            "global": global_challenge,
            "proposal": proposal,
        })

    async def challenge_accept(self, channel_id: int, proposal: dict) -> None:
        await self._send({"type": "CHALLENGE_ACCEPT", "channelId": channel_id, "proposal": proposal})

    async def challenge_decline(self, channel_id: int) -> None:
        await self._send({"type": "CHALLENGE_DECLINE", "channelId": channel_id})

    # --- Utility ---

    @property
    def username(self) -> Optional[str]:
        return self._username

    @property
    def user_rank(self) -> Optional[str]:
        return self._user_rank
