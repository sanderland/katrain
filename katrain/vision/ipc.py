"""IPC protocol between main process and vision worker.

Uses multiprocessing.Queue for commands (main→worker) and
multiprocessing.Queue for events (worker→main). Preview frames
are passed via a shared bytes buffer (overwrite semantics).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CommandType(Enum):
    """Commands sent from main process to vision worker."""

    SET_EXPECTED_BOARD = "set_expected_board"
    CONFIRM_POSE_LOCK = "confirm_pose_lock"
    RESET_SYNC = "reset_sync"
    ENTER_SETUP_MODE = "enter_setup_mode"
    BIND = "bind"
    UNBIND = "unbind"
    SET_VIEWER_ACTIVE = "set_viewer_active"
    SHUTDOWN = "shutdown"


@dataclass
class WorkerCommand:
    """Command sent by main process to worker."""

    action: CommandType
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerStatus:
    """Periodically published by worker to main process."""

    camera_status: str = "disconnected"  # "disconnected" | "connected"
    pose_lock_status: str = "unlocked"  # "unlocked" | "locked"
    sync_state: str = "unbound"  # SyncState value
    mean_confidence: float = 0.0
    detected_board: list[list[int]] | None = None  # 19x19 grid (0=empty, 1=black, 2=white)


@dataclass
class ConfirmedMove:
    """A confirmed move detected by the vision worker."""

    col: int
    row: int
    color: int  # BLACK=1, WHITE=2
