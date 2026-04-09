"""Abstract base class for all platform adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Awaitable, Callable, Optional

from katrain.web.platforms.models import (
    ClockState,
    OnlineUser,
    PlatformChallenge,
    PlatformCredentials,
    PlatformGameSession,
    PlatformMove,
    GamePhase,
)


class PlatformAdapter(ABC):
    """Base class for all platform adapters.

    Subclasses override capability flags to declare what they support,
    avoiding platform-specific branching in shared code.
    """

    platform_name: str = ""
    supported_board_sizes: list[int] = [19]

    # Capability declarations — subclasses override
    supports_live_play: bool = False
    supports_scoring: bool = False
    supports_automatch: bool = False
    supports_rooms: bool = False
    supports_seek_graph: bool = False

    def __init__(self):
        self._connected = False
        self._callbacks: dict[str, list[Callable]] = defaultdict(list)

    # --- Connection lifecycle ---

    @abstractmethod
    async def connect(self, credentials: PlatformCredentials) -> bool:
        """Authenticate and establish connection. Returns True on success."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Cleanly disconnect from the platform."""
        ...

    @property
    def is_connected(self) -> bool:
        return self._connected

    # --- Lobby ---

    async def get_online_users(self, room: Optional[str] = None) -> list[OnlineUser]:
        return []

    async def get_rooms(self) -> list[dict]:
        return []

    async def get_open_challenges(self) -> list[PlatformChallenge]:
        return []

    # --- Challenge ---

    async def send_challenge(self, user_id: str, settings: dict) -> str:
        raise NotImplementedError(f"{self.platform_name} does not support send_challenge")

    async def accept_challenge(self, challenge_id: str) -> PlatformGameSession:
        raise NotImplementedError(f"{self.platform_name} does not support accept_challenge")

    async def decline_challenge(self, challenge_id: str) -> None:
        raise NotImplementedError(f"{self.platform_name} does not support decline_challenge")

    async def create_open_challenge(self, settings: dict) -> str:
        raise NotImplementedError(f"{self.platform_name} does not support create_open_challenge")

    async def cancel_challenge(self, challenge_id: str) -> None:
        raise NotImplementedError(f"{self.platform_name} does not support cancel_challenge")

    async def start_automatch(self, preferences: dict) -> None:
        raise NotImplementedError(f"{self.platform_name} does not support automatch")

    async def cancel_automatch(self) -> None:
        raise NotImplementedError(f"{self.platform_name} does not support automatch")

    # --- In-game ---

    @abstractmethod
    async def submit_move(self, game_id: str, col: int, row: int) -> bool:
        """Submit a move to the platform. Returns True if accepted."""
        ...

    @abstractmethod
    async def submit_pass(self, game_id: str) -> bool:
        ...

    @abstractmethod
    async def resign(self, game_id: str) -> None:
        ...

    async def request_undo(self, game_id: str) -> None:
        raise NotImplementedError(f"{self.platform_name} does not support undo")

    async def accept_undo(self, game_id: str) -> None:
        raise NotImplementedError(f"{self.platform_name} does not support undo")

    async def fetch_game_snapshot(self, game_id: str) -> dict:
        """Fetch full game state from platform. Used for reconnection recovery."""
        raise NotImplementedError(f"{self.platform_name} does not support fetch_game_snapshot")

    async def submit_scoring_action(self, game_id: str, action: dict) -> bool:
        """Platform-specific scoring phase actions (mark dead stones, accept score, etc.)."""
        raise NotImplementedError(f"{self.platform_name} does not support scoring")

    # --- Event stream (callbacks) ---

    def on_opponent_move(self, callback: Callable[[PlatformMove], Awaitable[None]]) -> None:
        self._callbacks["opponent_move"].append(callback)

    def on_clock_update(self, callback: Callable[[ClockState], Awaitable[None]]) -> None:
        self._callbacks["clock_update"].append(callback)

    def on_challenge_received(self, callback: Callable[[PlatformChallenge], Awaitable[None]]) -> None:
        self._callbacks["challenge_received"].append(callback)

    def on_game_started(self, callback: Callable[[PlatformGameSession], Awaitable[None]]) -> None:
        self._callbacks["game_started"].append(callback)

    def on_game_ended(self, callback: Callable[[str, str, str], Awaitable[None]]) -> None:
        """game_id, result, winner"""
        self._callbacks["game_ended"].append(callback)

    def on_game_phase_changed(self, callback: Callable[[str, GamePhase], Awaitable[None]]) -> None:
        self._callbacks["game_phase_changed"].append(callback)

    def on_automatch_found(self, callback: Callable[[PlatformGameSession], Awaitable[None]]) -> None:
        self._callbacks["automatch_found"].append(callback)

    def on_connection_lost(self, callback: Callable[[], Awaitable[None]]) -> None:
        self._callbacks["connection_lost"].append(callback)

    def on_reconnected(self, callback: Callable[[], Awaitable[None]]) -> None:
        self._callbacks["reconnected"].append(callback)

    def on_auth_expired(self, callback: Callable[[], Awaitable[None]]) -> None:
        self._callbacks["auth_expired"].append(callback)

    def on_token_refreshed(self, callback: Callable[[dict], Awaitable[None]]) -> None:
        self._callbacks["token_refreshed"].append(callback)

    # --- Internal callback dispatch ---

    async def _emit(self, event: str, *args) -> None:
        for cb in self._callbacks.get(event, []):
            await cb(*args)
