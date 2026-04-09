"""OGS real-time WebSocket client.

Manages the native WebSocket connection to OGS for live game events.
OGS has migrated from socket.io to native WebSocket (as of 2025).

Wire format (native WebSocket, JSON arrays):
  Client → Server: [command, data?, request_id?]
  Server → Client: [event_name, data] or [request_id, data?, error?]

Key events:
  - game/{id}/gamedata: Full game state on connect
  - game/{id}/move: Opponent move {game_id, move_number, move: [x, y, timedelta?, color?]}
  - game/{id}/clock: Timer update
  - game/{id}/phase: Phase change (play/stone removal/finished)
  - active_game: Active game notification
  - notification: Challenge notifications
  - seekgraph/global: Open challenges
  - automatch/start: Automatch found {uuid, game_id}
  - net/pong: Latency measurement
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from typing import Callable, Optional

logger = logging.getLogger("katrain_web")

OGS_WS_URL = "wss://online-go.com"


class OGSRealtimeClient:
    """Native WebSocket client for OGS real-time events.

    Uses plain WebSocket with JSON array wire format,
    matching the current goban library GobanSocket implementation.
    """

    def __init__(self, ws_url: str = OGS_WS_URL):
        self._ws_url = ws_url
        self._ws = None
        self._connected = False
        self._authenticated = asyncio.Event()
        self._callbacks: dict[str, list[Callable]] = defaultdict(list)
        self._pending_requests: dict[int, asyncio.Future] = {}
        self._request_id: int = 0
        self._latency: float = 0
        self._drift: float = 0
        self._ping_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._user_id: Optional[int] = None
        self._username: Optional[str] = None
        self._jwt: Optional[str] = None  # Stored for reconnection
        self._connected_games: set[int] = set()
        self._intentional_disconnect: bool = False
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = 20
        self._seek_graph_connected: bool = False

    # --- Connection lifecycle ---

    async def connect(self, jwt: str, user_id: int, username: str) -> None:
        """Connect to OGS native WebSocket and authenticate."""
        self._user_id = user_id
        self._username = username
        self._jwt = jwt
        self._intentional_disconnect = False
        self._reconnect_attempts = 0

        await self._establish_connection(jwt)

    async def _establish_connection(self, jwt: str) -> None:
        """Internal: establish WebSocket connection and authenticate."""
        import websockets

        logger.info(f"Connecting to OGS realtime: {self._ws_url}")
        self._ws = await websockets.connect(
            self._ws_url,
            additional_headers={"Origin": "https://online-go.com"},
            ping_interval=20,
            ping_timeout=10,
        )

        self._connected = True

        # Start receive loop before authenticating (we need to receive the response)
        self._receive_task = asyncio.create_task(self._receive_loop())

        # Authenticate with request_id to get response
        auth_response = await self._send_with_response("authenticate", {
            "jwt": jwt,
            "client": "KaTrain-SmartBoard",
            "client_version": "0.1",
        })
        logger.debug(f"Auth response: {auth_response}")
        self._authenticated.set()

        # Start application-level ping loop (10s interval for clock sync)
        self._ping_task = asyncio.create_task(self._net_ping_loop())

        logger.info(f"OGS realtime connected and authenticated as {self._username}")

    async def disconnect(self) -> None:
        """Cleanly disconnect from OGS."""
        self._intentional_disconnect = True
        self._connected = False
        self._authenticated.clear()
        for task in [self._receive_task, self._ping_task, self._reconnect_task]:
            if task:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._connected_games.clear()
        self._seek_graph_connected = False
        # Cancel any pending request futures
        for fut in self._pending_requests.values():
            if not fut.done():
                fut.cancel()
        self._pending_requests.clear()
        logger.info("OGS realtime disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None

    # --- Native WebSocket message encoding ---

    async def _send(self, command: str, data=None) -> None:
        """Send a command. Format: [command, data]"""
        if data is not None:
            msg = json.dumps([command, data])
        else:
            msg = json.dumps([command])
        await self._ws.send(msg)

    async def _send_with_response(self, command: str, data=None, timeout: float = 10.0):
        """Send a command with request_id and wait for response."""
        self._request_id += 1
        req_id = self._request_id
        fut = asyncio.get_event_loop().create_future()
        self._pending_requests[req_id] = fut

        if data is not None:
            msg = json.dumps([command, data, req_id])
        else:
            msg = json.dumps([command, req_id])
        await self._ws.send(msg)

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            raise
        finally:
            self._pending_requests.pop(req_id, None)

    # --- Receive loop ---

    async def _receive_loop(self) -> None:
        """Main receive loop for native WebSocket messages."""
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Non-JSON message from OGS: {str(raw)[:100]}")
                    continue

                if not isinstance(msg, list) or len(msg) < 1:
                    continue

                first = msg[0]
                if isinstance(first, str):
                    # Event message: [event_name, data]
                    event = first
                    data = msg[1] if len(msg) > 1 else None
                    await self._dispatch(event, data)
                elif isinstance(first, int):
                    # Response to a request: [request_id, data?, error?]
                    req_id = first
                    data = msg[1] if len(msg) > 1 else None
                    error = msg[2] if len(msg) > 2 else None
                    fut = self._pending_requests.get(req_id)
                    if fut and not fut.done():
                        if error:
                            fut.set_exception(RuntimeError(f"OGS error: {error}"))
                        else:
                            fut.set_result(data)
        except Exception as e:
            if self._connected:
                logger.error(f"OGS receive loop error: {e}")
                self._connected = False
                self._authenticated.clear()
                await self._dispatch("_connection_lost", None)
                if not self._intentional_disconnect:
                    self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _dispatch(self, event: str, data) -> None:
        """Dispatch event to registered callbacks."""
        handlers = self._callbacks.get(event, [])
        if not handlers and not event.startswith("net/"):
            logger.debug(f"OGS event '{event}' has no handlers (data type: {type(data).__name__})")
        for cb in handlers:
            try:
                result = cb(data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Error in callback for {event}: {e}")

    # --- Event registration ---

    def on(self, event: str, handler: Callable) -> None:
        """Register a callback for a WebSocket event."""
        self._callbacks[event].append(handler)

    # --- Game connection ---

    async def game_connect(self, game_id: int) -> None:
        """Connect to a game's event stream."""
        await self._send("game/connect", {"game_id": game_id, "chat": False})
        self._connected_games.add(game_id)
        logger.debug(f"Connected to OGS game {game_id}")

    async def game_disconnect(self, game_id: int) -> None:
        """Disconnect from a game's event stream."""
        await self._send("game/disconnect", {"game_id": game_id})
        self._connected_games.discard(game_id)

    # --- Game actions ---

    async def game_move(self, game_id: int, move: str) -> None:
        """Submit a move. `move` uses OGS coordinate encoding (a=0, b=1, ...) or '..' for pass."""
        await self._send("game/move", {"game_id": game_id, "move": move})

    async def game_resign(self, game_id: int) -> None:
        """Resign the current game."""
        await self._send("game/resign", {"game_id": game_id})

    async def game_removed_stones_set(self, game_id: int, stones: str, removed: bool = True) -> None:
        """Mark/unmark stones as dead during scoring phase."""
        await self._send("game/removed_stones/set", {
            "game_id": game_id,
            "removed": removed,
            "stones": stones,
        })

    async def game_removed_stones_accept(self, game_id: int, stones: str) -> None:
        """Accept the current dead stone selection during scoring phase."""
        await self._send("game/removed_stones/accept", {
            "game_id": game_id,
            "stones": stones,
            "strict_seki_mode": False,
        })

    async def game_removed_stones_reject(self, game_id: int) -> None:
        """Reject dead stone selection and resume play."""
        await self._send("game/removed_stones/reject", {"game_id": game_id})

    # --- Seek graph / automatch ---

    async def seek_graph_connect(self) -> None:
        """Connect to the global seek graph for open challenges."""
        await self._send("seek_graph/connect", {"channel": "global"})
        self._seek_graph_connected = True

    async def seek_graph_disconnect(self) -> None:
        await self._send("seek_graph/disconnect", {"channel": "global"})
        self._seek_graph_connected = False

    async def automatch_find(self, preferences: dict) -> str:
        """Start automatch. Returns the automatch UUID."""
        match_uuid = str(uuid.uuid4())
        await self._send("automatch/find_match", {
            "uuid": match_uuid,
            "size_speed_options": preferences.get("size_speed_options", [
                {"size": "19x19", "speed": "live"},
            ]),
            "lower_rank_diff": preferences.get("lower_rank_diff", 3),
            "upper_rank_diff": preferences.get("upper_rank_diff", 3),
            "rules": {"condition": "no-preference", "value": "chinese"},
            "handicap": {"condition": "no-preference", "value": "enabled"},
        })
        return match_uuid

    async def automatch_cancel(self, match_uuid: str) -> None:
        await self._send("automatch/cancel", {"uuid": match_uuid})

    # --- Reconnection ---

    async def _reconnect_loop(self) -> None:
        """Auto-reconnect with exponential backoff. Re-joins games and seek graph."""
        while not self._intentional_disconnect and self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1
            delay = min(2 ** self._reconnect_attempts, 60)  # 2s, 4s, 8s, ..., max 60s
            logger.info(f"OGS reconnect attempt {self._reconnect_attempts} in {delay}s")
            await asyncio.sleep(delay)

            if self._intentional_disconnect:
                break

            try:
                # Cancel old tasks
                for task in [self._receive_task, self._ping_task]:
                    if task:
                        task.cancel()
                        try:
                            await task
                        except (asyncio.CancelledError, Exception):
                            pass
                if self._ws:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None

                # Re-establish connection
                await self._establish_connection(self._jwt)
                self._reconnect_attempts = 0

                # Re-join active games
                games_to_rejoin = set(self._connected_games)
                for game_id in games_to_rejoin:
                    try:
                        await self.game_connect(game_id)
                    except Exception as e:
                        logger.warning(f"Failed to rejoin game {game_id}: {e}")

                # Re-join seek graph if was connected
                if self._seek_graph_connected:
                    try:
                        await self.seek_graph_connect()
                    except Exception as e:
                        logger.warning(f"Failed to rejoin seek graph: {e}")

                await self._dispatch("_reconnected", None)
                logger.info("OGS reconnected successfully")
                return

            except Exception as e:
                logger.warning(f"OGS reconnect attempt {self._reconnect_attempts} failed: {e}")
                self._connected = False
                self._authenticated.clear()

        if not self._intentional_disconnect:
            logger.error(f"OGS reconnection failed after {self._max_reconnect_attempts} attempts")

    # --- Ping / latency ---

    async def _net_ping_loop(self) -> None:
        """Application-level ping for latency/clock sync (10s interval)."""
        while self._connected:
            try:
                await self._send("net/ping", {
                    "client": int(time.time() * 1000),
                    "drift": self._drift,
                    "latency": self._latency,
                })
                await asyncio.sleep(10)
            except (asyncio.CancelledError, Exception):
                break

    # --- Utility ---

    @property
    def latency(self) -> float:
        return self._latency

    @latency.setter
    def latency(self, value: float) -> None:
        self._latency = value

    @property
    def drift(self) -> float:
        return self._drift

    @drift.setter
    def drift(self, value: float) -> None:
        self._drift = value
