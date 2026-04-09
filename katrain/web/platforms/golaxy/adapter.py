"""Golaxy / 星阵围棋 (19x19.com) platform adapter.

REST API for game actions + STOMP over SockJS for real-time events.
Auth: phone-only (+86 Chinese mobile number).
"""

from __future__ import annotations

import base64
import logging
from typing import Optional

import httpx

from katrain.web.platforms.base import PlatformAdapter
from katrain.web.platforms.models import (
    ClockState,
    GamePhase,
    OnlineUser,
    PlatformChallenge,
    PlatformCredentials,
    PlatformGameSession,
    PlatformMove,
    TimeControl,
)

logger = logging.getLogger("katrain_web")

GOLAXY_API_BASE = "https://api.19x19.com"
GOLAXY_WEB_BASE = "https://www.19x19.com"
GOLAXY_WS = "wss://ws.19x19.com/api/social/channel/WS_STOMP_ENDPOINT_GOLAXY"
GOLAXY_CLIENT_CREDENTIALS = base64.b64encode(b"golaxy_web:xingzhen0730").decode()


class GolaxyRestClient:
    """HTTP client for Golaxy REST API."""

    def __init__(self, base_url: str = GOLAXY_API_BASE):
        self._base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._user_code: Optional[str] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=30.0,
                headers={"User-Agent": "KaTrain-SmartBoard/0.1"},
            )
        return self._client

    def _auth_headers(self) -> dict:
        if self._access_token:
            return {"Authorization": f"Bearer {self._access_token}"}
        return {}

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # --- Auth ---

    async def login_password(self, phone: str, password: str) -> dict:
        """Login with phone number and password."""
        client = await self._ensure_client()
        resp = await client.post(
            "/api/auth/oauth/token",
            data={
                "username": f"0086-{phone}",
                "password": password,
                "grant_type": "password",
                "client_id": "golaxy_web",
                "scope": "any",
            },
            headers={
                "Authorization": f"Basic {GOLAXY_CLIENT_CREDENTIALS}",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data.get("access_token")
        self._refresh_token = data.get("refresh_token")
        return data

    async def login_sms(self, phone: str, code: str) -> dict:
        """Login with phone number and SMS verification code.

        Verified format from browser capture:
          username=0086-{phone}&password=null&grant_type=sms_code&client_id=golaxy_web&sms_code={code}&scope=any
        """
        client = await self._ensure_client()
        resp = await client.post(
            "/api/auth/oauth/token",
            data={
                "username": f"0086-{phone}",
                "password": "null",
                "grant_type": "sms_code",
                "client_id": "golaxy_web",
                "sms_code": code,
                "scope": "any",
            },
            headers={
                "Authorization": f"Basic {GOLAXY_CLIENT_CREDENTIALS}",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data.get("access_token")
        self._refresh_token = data.get("refresh_token")
        return data

    async def request_sms_code(self, phone: str) -> bool:
        """Request SMS verification code."""
        client = await self._ensure_client()
        resp = await client.get("/api/auth/sms/code", params={"username": phone, "login": "true", "area": "0086"},
                                headers={"Authorization": f"Basic {GOLAXY_CLIENT_CREDENTIALS}",
                                         "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        return resp.status_code == 200

    async def refresh_access_token(self) -> dict:
        """Refresh the access token."""
        client = await self._ensure_client()
        resp = await client.post(
            "/api/auth/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": "golaxy_web",
                "refresh_token": self._refresh_token,
            },
            headers={
                "Authorization": f"Basic {GOLAXY_CLIENT_CREDENTIALS}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data.get("access_token")
        self._refresh_token = data.get("refresh_token")
        return data

    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        self._access_token = access_token
        self._refresh_token = refresh_token

    def get_auth_data(self) -> dict:
        return {"access_token": self._access_token, "refresh_token": self._refresh_token, "user_code": self._user_code}

    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None

    # --- Game service ---

    async def create_gameroom(self, settings: dict) -> dict:
        client = await self._ensure_client()
        resp = await client.post("/api/social/gameroom/reserve", json=settings, headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def join_gameroom(self, room_id: str) -> dict:
        client = await self._ensure_client()
        resp = await client.post(f"/api/social/gameroom/login/{room_id}", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def leave_gameroom(self, room_id: str) -> None:
        client = await self._ensure_client()
        await client.post(f"/api/social/gameroom/logout/{room_id}", headers=self._auth_headers())

    async def start_game(self, game_id: str) -> dict:
        client = await self._ensure_client()
        resp = await client.post(f"/api/social/wsgame/start/{game_id}", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def submit_move(self, game_id: str, move_data: dict) -> dict:
        client = await self._ensure_client()
        resp = await client.post(f"/api/social/wsgame/genmove/{game_id}", json=move_data, headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def request_undo(self, game_id: str) -> dict:
        client = await self._ensure_client()
        resp = await client.post(f"/api/social/wsgame/backmove/{game_id}", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def end_game(self, game_id: str) -> dict:
        client = await self._ensure_client()
        resp = await client.post(f"/api/social/wsgame/game/end/{game_id}", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def get_game_state(self, game_id: str) -> dict:
        client = await self._ensure_client()
        resp = await client.get(f"/api/social/wsgame/game/state/{game_id}", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def get_game_meta(self, game_id: str) -> dict:
        client = await self._ensure_client()
        resp = await client.get(f"/api/social/wsgame/game/meta/{game_id}", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    # --- Live/spectating (no auth required) ---

    async def get_all_lives(self) -> list[dict]:
        client = await self._ensure_client()
        resp = await client.get("/api/engine/golives/all")
        resp.raise_for_status()
        return resp.json()

    async def get_live_moves(self, live_id: str, begin: int = 0, end: int = 500) -> dict:
        client = await self._ensure_client()
        resp = await client.get(
            f"/api/engine/golives/base/{live_id}", params={"begin_move_num": begin, "end_move_num": end}
        )
        resp.raise_for_status()
        return resp.json()

    async def get_live_sgf(self, game_id: str) -> str:
        client = await self._ensure_client()
        resp = await client.get(f"/api/engine/golives/{game_id}")
        resp.raise_for_status()
        return resp.text


class GolaxyAdapter(PlatformAdapter):
    """PlatformAdapter implementation for Golaxy / 星阵围棋 (19x19.com).

    REST API for game actions. STOMP over SockJS for real-time events.
    Note: Live play via STOMP requires capturing payload schemas from browser traffic.
    Currently provides REST-based game flow (higher latency than WebSocket).
    """

    platform_name = "golaxy"
    supported_board_sizes = [9, 13, 19]
    supports_live_play = True
    supports_scoring = False  # Scoring handled server-side via judge endpoint
    supports_automatch = False  # TODO: verify automatch support
    supports_rooms = True
    supports_seek_graph = False

    def __init__(self):
        super().__init__()
        self._rest = GolaxyRestClient()
        self._active_game_id: Optional[str] = None

    async def connect(self, credentials: PlatformCredentials) -> bool:
        try:
            auth_data = credentials.auth_data
            if "access_token" in auth_data and auth_data["access_token"]:
                # Try token-based reconnection
                self._rest.set_tokens(auth_data["access_token"], auth_data.get("refresh_token", ""))
                try:
                    # Verify token is still valid by making a test request
                    await self._rest.get_all_lives()
                    self._connected = True
                    return True
                except Exception:
                    # Token expired, try refresh
                    if auth_data.get("refresh_token"):
                        try:
                            await self._rest.refresh_access_token()
                            self._connected = True
                            await self._emit("token_refreshed", self._rest.get_auth_data())
                            return True
                        except Exception:
                            pass

            # Fall through to password login
            password = auth_data.get("password", "")
            if password:
                await self._rest.login_password(credentials.username, password)
                self._connected = True
                await self._emit("token_refreshed", self._rest.get_auth_data())
                logger.info(f"Golaxy connected as {credentials.username}")
                return True

            return False
        except Exception as e:
            logger.error(f"Golaxy connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        await self._rest.close()
        self._connected = False
        self._active_game_id = None

    async def get_rooms(self) -> list[dict]:
        # Golaxy rooms are created on-demand; no global room list
        return []

    async def submit_move(self, game_id: str, col: int, row: int) -> bool:
        try:
            # Golaxy move format TBD — likely {"x": col, "y": row} or similar
            await self._rest.submit_move(game_id, {"x": col, "y": row})
            return True
        except Exception as e:
            logger.error(f"Golaxy move submission failed: {e}")
            return False

    async def submit_pass(self, game_id: str) -> bool:
        try:
            await self._rest.submit_move(game_id, {"pass": True})
            return True
        except Exception as e:
            logger.error(f"Golaxy pass failed: {e}")
            return False

    async def resign(self, game_id: str) -> None:
        await self._rest.end_game(game_id)

    async def fetch_game_snapshot(self, game_id: str) -> dict:
        return await self._rest.get_game_state(game_id)
