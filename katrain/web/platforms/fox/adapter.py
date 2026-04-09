"""Fox Weiqi (野狐围棋) platform adapter.

Connects via the openfoxwq WebSocket proxy to Fox servers.
Protocol: protobuf over WebSocket.

NOTE: This adapter requires protobuf definitions reconstructed from
openfoxwq_client Dart-generated code. Until those are available,
this adapter provides the structural skeleton with REST-only fallback.
"""

from __future__ import annotations

import hashlib
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

FOX_REST_API = "https://foxwq-8e6797d8dbb9.herokuapp.com/api/v1"
FOX_WS_PROXY = "wss://api.openfoxwq.com"

# Fox rank mapping
_FOX_RANKS = {}
for i in range(18):
    _FOX_RANKS[i] = (f"{18 - i}k", float(12 + i))
for i in range(10):
    _FOX_RANKS[18 + i] = (f"{i + 1}d", float(30 + i))
for i in range(10):
    _FOX_RANKS[28 + i] = (f"{i + 1}p", float(40 + i))


def _parse_fox_rank(rank_value: int) -> tuple[str, float]:
    """Convert Fox rank enum value to display rank and numeric."""
    return _FOX_RANKS.get(rank_value, ("?", 0.0))


def _md5_password(password: str) -> str:
    """MD5 hex digest of password (Fox auth requirement)."""
    return hashlib.md5(password.encode("utf-8")).hexdigest()


class FoxRestClient:
    """Read-only REST client for openfoxwq API proxy."""

    def __init__(self, base_url: str = FOX_REST_API):
        self._base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None
        self._headers: dict = {}

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=30.0,
                headers={"User-Agent": "KaTrain-SmartBoard/0.1", **self._headers},
            )
        return self._client

    def set_auth(self, username: str, password_md5: str) -> None:
        import base64

        basic = base64.b64encode(f"{username}:{password_md5}".encode()).decode()
        self._headers["Authorization"] = f"Basic {basic}"

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_me(self) -> dict:
        client = await self._ensure_client()
        resp = await client.get("/me")
        resp.raise_for_status()
        return resp.json()

    async def get_player(self, player_id: int) -> dict:
        client = await self._ensure_client()
        resp = await client.get(f"/players/{player_id}")
        resp.raise_for_status()
        return resp.json()

    async def search_players(self, nick: str) -> list[dict]:
        client = await self._ensure_client()
        resp = await client.get("/players", params={"nick": nick})
        resp.raise_for_status()
        return resp.json()

    async def get_player_games(self, player_id: int) -> list[dict]:
        client = await self._ensure_client()
        resp = await client.get(f"/players/{player_id}/games")
        resp.raise_for_status()
        return resp.json()

    async def get_game_sgf(self, game_id: int) -> str:
        client = await self._ensure_client()
        resp = await client.get(f"/games/{game_id}")
        resp.raise_for_status()
        return resp.text

    async def get_top_games(self) -> list[dict]:
        client = await self._ensure_client()
        resp = await client.get("/top_games")
        resp.raise_for_status()
        return resp.json()


class FoxAdapter(PlatformAdapter):
    """PlatformAdapter implementation for Fox Weiqi (野狐围棋).

    Currently provides REST-only access (read-only: player search, game history, SGF).
    Live play requires the protobuf WebSocket client (TODO: reconstruct .proto files).
    """

    platform_name = "fox"
    supported_board_sizes = [9, 13, 19]
    supports_live_play = False  # TODO: enable after protobuf client is ready
    supports_scoring = False
    supports_automatch = False
    supports_rooms = True
    supports_seek_graph = False

    def __init__(self):
        super().__init__()
        self._rest = FoxRestClient()
        self._player_id: Optional[int] = None
        self._username: Optional[str] = None

    async def connect(self, credentials: PlatformCredentials) -> bool:
        try:
            password_md5 = _md5_password(credentials.auth_data.get("password", ""))
            self._rest.set_auth(credentials.username, password_md5)
            me = await self._rest.get_me()
            self._player_id = me.get("id") or me.get("player_id")
            self._username = credentials.username
            self._connected = True
            logger.info(f"Fox REST connected as {self._username}")
            return True
        except Exception as e:
            logger.error(f"Fox connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        await self._rest.close()
        self._connected = False
        self._player_id = None

    async def get_online_users(self, room: Optional[str] = None) -> list[OnlineUser]:
        # REST proxy doesn't support online user listing
        return []

    async def get_rooms(self) -> list[dict]:
        # Rooms require live WebSocket connection
        return []

    async def submit_move(self, game_id: str, col: int, row: int) -> bool:
        raise NotImplementedError("Fox live play requires protobuf WebSocket client (not yet implemented)")

    async def submit_pass(self, game_id: str) -> bool:
        raise NotImplementedError("Fox live play requires protobuf WebSocket client (not yet implemented)")

    async def resign(self, game_id: str) -> None:
        raise NotImplementedError("Fox live play requires protobuf WebSocket client (not yet implemented)")
