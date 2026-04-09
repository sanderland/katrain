"""Shared data models for cross-platform online play.

All platform adapters use these models for a consistent interface.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class GamePhase(str, Enum):
    PLAYING = "playing"
    PAUSED = "paused"
    SCORING = "scoring"
    FINISHED = "finished"


@dataclass
class PlatformCredentials:
    platform: str
    username: str
    auth_data: dict = field(default_factory=dict)


@dataclass
class OnlineUser:
    platform: str
    user_id: str
    username: str
    rank: str
    rank_numeric: float
    status: str = "idle"  # "idle", "playing", "away"


@dataclass
class TimeControl:
    system: str  # "byoyomi", "fischer", "canadian", "absolute", "simple"
    main_time: int  # seconds
    period_time: Optional[int] = None  # byo-yomi
    periods: Optional[int] = None  # byo-yomi
    time_increment: Optional[int] = None  # fischer
    max_time: Optional[int] = None  # fischer
    stones_per_period: Optional[int] = None  # canadian


@dataclass
class ClockState:
    black_time: dict
    white_time: dict
    current_player: str  # "B" or "W"
    paused: bool = False


@dataclass
class PlatformMove:
    col: int  # 0-indexed from left
    row: int  # 0-indexed from top
    color: str  # "B" or "W"
    move_number: int


@dataclass
class PlatformChallenge:
    platform: str
    challenge_id: str
    from_user: OnlineUser
    board_size: int
    time_control: TimeControl
    rules: str  # "chinese", "japanese", "korean", "aga"
    ranked: bool
    handicap: int
    komi: Optional[float] = None  # None = automatic


@dataclass
class PlatformGameSession:
    platform: str
    game_id: str
    board_size: int
    my_color: str  # "B" or "W"
    opponent: OnlineUser
    time_control: TimeControl
    rules: str
    ranked: bool
    handicap: int
    komi: float


@dataclass
class PlatformGameContext:
    """Tracks the bridge state between a platform game and a local KaTrain session.

    Remote platform is the source of truth for game state.
    """

    session_id: str
    platform: str
    remote_game_id: str
    game_phase: GamePhase = GamePhase.PLAYING
    last_confirmed_move: int = 0
    pending_action: Optional[str] = None  # "move", "pass", "resign", None
    pending_action_timestamp: Optional[float] = None
    remote_clock_version: int = 0
    needs_resync: bool = False
    my_color: str = "B"

    def recover_from_snapshot(self, snapshot: dict) -> None:
        """Reset local state from a full game snapshot fetched after reconnection."""
        self.game_phase = GamePhase(snapshot.get("phase", "playing"))
        self.last_confirmed_move = snapshot.get("move_number", 0)
        self.pending_action = None
        self.pending_action_timestamp = None
        self.needs_resync = False

    def set_pending(self, action: str) -> None:
        self.pending_action = action
        self.pending_action_timestamp = time.time()

    def clear_pending(self) -> None:
        self.pending_action = None
        self.pending_action_timestamp = None

    @property
    def is_pending(self) -> bool:
        return self.pending_action is not None

    @property
    def pending_timed_out(self) -> bool:
        if self.pending_action_timestamp is None:
            return False
        return (time.time() - self.pending_action_timestamp) > 5.0
