"""Vision service — main-process controller for the vision worker.

This is a thin proxy that manages the worker lifecycle, relays commands,
and polls for events/moves. It does NOT run inference directly.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

import numpy as np

from katrain.vision.config_service import VisionServiceConfig
from katrain.vision.ipc import CommandType, ConfirmedMove, WorkerCommand, WorkerStatus
from katrain.vision.sync import game_state_stones_to_board

logger = logging.getLogger(__name__)


class VisionService:
    """Main-process controller for the vision worker."""

    def __init__(self, config: VisionServiceConfig):
        self._config = config
        self._worker = None  # VisionWorkerProcess | InProcessAdapter
        self._bound_session_id: str | None = None
        self._event_callbacks: list[Callable] = []
        self._latest_status: WorkerStatus = WorkerStatus()

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Spawn the vision worker (subprocess or in-process thread)."""
        worker_config = self._config.to_worker_config()

        if self._config.process_mode == "inprocess":
            from katrain.vision.worker_inprocess import InProcessAdapter

            self._worker = InProcessAdapter(worker_config)
        else:
            from katrain.vision.worker import VisionWorkerProcess

            self._worker = VisionWorkerProcess(worker_config)

        self._worker.start()
        logger.info("VisionService started (mode=%s)", self._config.process_mode)

    def stop(self) -> None:
        """Stop the vision worker."""
        if self._worker:
            self._worker.stop()
            self._worker = None
        logger.info("VisionService stopped")

    # -- status --------------------------------------------------------------

    @property
    def camera_status(self) -> str:
        return self._latest_status.camera_status

    @property
    def pose_lock_status(self) -> str:
        return self._latest_status.pose_lock_status

    @property
    def sync_state(self) -> str:
        return self._latest_status.sync_state

    @property
    def bound_session_id(self) -> str | None:
        return self._bound_session_id

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def refresh_status(self) -> None:
        """Pull latest status from worker."""
        if self._worker:
            status = self._worker.get_status()
            if status is not None:
                self._latest_status = status

    # -- commands ------------------------------------------------------------

    def confirm_pose_lock(self) -> bool:
        """Send confirm pose lock command to worker."""
        if not self._worker:
            return False
        self._worker.send_command(WorkerCommand(action=CommandType.CONFIRM_POSE_LOCK))
        return True

    def set_expected_board(self, board: np.ndarray) -> None:
        """Update expected board for sync comparison."""
        if self._worker:
            self._worker.send_command(
                WorkerCommand(action=CommandType.SET_EXPECTED_BOARD, data={"board": board.tolist()})
            )

    def set_expected_from_stones(self, stones: list[list], board_size: int = 19) -> None:
        """Convert GameState.stones to board matrix and set as expected."""
        board = game_state_stones_to_board(stones, board_size)
        self.set_expected_board(board)

    def enter_setup_mode(self, target_board: np.ndarray) -> None:
        """Enter tsumego setup mode with target position."""
        if self._worker:
            self._worker.send_command(
                WorkerCommand(action=CommandType.ENTER_SETUP_MODE, data={"target_board": target_board.tolist()})
            )

    def reset_sync(self) -> None:
        """Accept current physical board as new baseline."""
        if self._worker:
            self._worker.send_command(WorkerCommand(action=CommandType.RESET_SYNC))

    def bind_session(self, session_id: str) -> None:
        """Bind vision to a game session."""
        self._bound_session_id = session_id
        if self._worker:
            self._worker.send_command(WorkerCommand(action=CommandType.BIND))

    def unbind_session(self) -> None:
        """Unbind from current session."""
        self._bound_session_id = None
        if self._worker:
            self._worker.send_command(WorkerCommand(action=CommandType.UNBIND))

    def set_viewer_active(self, active: bool) -> None:
        """Tell worker whether MJPEG viewers are connected."""
        if self._worker:
            self._worker.send_command(
                WorkerCommand(action=CommandType.SET_VIEWER_ACTIVE, data={"active": active})
            )

    # -- data retrieval ------------------------------------------------------

    def get_detected_board(self) -> list[list[int]] | None:
        """Return the latest detected board state (19x19 grid)."""
        return self._latest_status.detected_board

    def get_preview_jpeg(self) -> bytes | None:
        """Get latest JPEG preview frame from worker."""
        if self._worker:
            return self._worker.get_preview_jpeg()
        return None

    def poll_events(self) -> list[Any]:
        """Read all pending events from worker."""
        events = []
        if not self._worker:
            return events
        while True:
            evt = self._worker.get_event()
            if evt is None:
                break
            events.append(evt)
        return events

    def get_confirmed_move(self) -> ConfirmedMove | None:
        """Read and consume the latest confirmed move from events.

        Scans pending events for ConfirmedMove instances. Non-move events
        are re-queued (they'll be picked up by poll_events).
        """
        events = self.poll_events()
        move = None
        others = []
        for evt in events:
            if isinstance(evt, ConfirmedMove):
                move = evt  # Keep the latest
            else:
                others.append(evt)
        # Re-queue non-move events — not ideal but keeps the interface simple.
        # A proper implementation would use separate queues.
        if self._worker:
            for evt in others:
                self._worker._event_queue.put(evt)
        return move

    @property
    def is_alive(self) -> bool:
        return self._worker is not None and self._worker.is_alive
