"""Platform Command Gateway — intercepts game commands for platform-backed sessions.

For platform games: submit to remote platform -> wait for ACK -> apply locally.
For local games: pass through to KaTrain directly (existing behavior).
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from katrain.web.platforms.manager import PlatformManager
from katrain.web.platforms.models import PlatformGameContext

logger = logging.getLogger("katrain_web")

PLATFORM_ACK_TIMEOUT = 5.0  # seconds


class PlatformMoveRejectedError(Exception):
    """Raised when the platform rejects a submitted move."""

    pass


class PlatformCommandGateway:
    """Intercepts game commands for platform-backed sessions.

    For platform games: submit to remote platform -> wait for ACK -> apply locally.
    For local games: pass through to KaTrain directly (existing behavior).
    """

    def __init__(self, platform_manager: PlatformManager, session_manager):
        self._pm = platform_manager
        self._sm = session_manager

    def is_platform_game(self, session_id: str) -> bool:
        return self._pm.is_platform_game(session_id)

    async def play_move(self, session_id: str, col: int, row: int, user_id: int) -> dict:
        ctx = self._pm.get_game_context(session_id)
        if ctx is None:
            return self._local_play(session_id, col, row)

        if ctx.is_pending:
            raise PlatformMoveRejectedError("Previous move still pending")

        # Platform game — remote first
        ctx.set_pending("move")
        self._broadcast_pending(session_id, col, row)

        adapter = self._pm.get_adapter(ctx.platform)
        try:
            success = await adapter.submit_move(ctx.remote_game_id, col, row)
        except Exception as e:
            logger.error(f"Platform move submission failed: {e}")
            ctx.clear_pending()
            self._broadcast_rejected(session_id, str(e))
            raise PlatformMoveRejectedError(str(e))

        if success:
            ctx.clear_pending()
            ctx.last_confirmed_move += 1
            result = self._local_play(session_id, col, row)
            self._broadcast_confirmed(session_id, col, row, ctx.last_confirmed_move)
            return result
        else:
            ctx.clear_pending()
            self._broadcast_rejected(session_id, "move_rejected")
            raise PlatformMoveRejectedError("Platform rejected the move")

    async def pass_move(self, session_id: str, user_id: int) -> dict:
        ctx = self._pm.get_game_context(session_id)
        if ctx is None:
            return self._local_pass(session_id)

        if ctx.is_pending:
            raise PlatformMoveRejectedError("Previous action still pending")

        ctx.set_pending("pass")
        adapter = self._pm.get_adapter(ctx.platform)
        try:
            success = await adapter.submit_pass(ctx.remote_game_id)
        except Exception as e:
            ctx.clear_pending()
            raise PlatformMoveRejectedError(str(e))

        if success:
            ctx.clear_pending()
            return self._local_pass(session_id)
        else:
            ctx.clear_pending()
            raise PlatformMoveRejectedError("Platform rejected pass")

    async def resign(self, session_id: str, user_id: int) -> dict:
        ctx = self._pm.get_game_context(session_id)
        if ctx is None:
            return self._local_resign(session_id)

        ctx.set_pending("resign")
        adapter = self._pm.get_adapter(ctx.platform)
        try:
            await adapter.resign(ctx.remote_game_id)
        except Exception as e:
            ctx.clear_pending()
            raise PlatformMoveRejectedError(str(e))

        ctx.clear_pending()
        return self._local_resign(session_id)

    async def request_count(self, session_id: str, user_id: int) -> dict:
        """Route to platform scoring phase if supported."""
        ctx = self._pm.get_game_context(session_id)
        if ctx is None:
            # Local game — use existing count logic
            return {"status": "local_count"}

        adapter = self._pm.get_adapter(ctx.platform)
        if adapter.supports_scoring:
            # Platform handles scoring; relay to adapter
            await adapter.submit_scoring_action(ctx.remote_game_id, {"action": "request_count"})
            return {"status": "platform_scoring_requested"}
        return {"status": "scoring_not_supported"}

    # --- Local passthrough ---

    def _local_play(self, session_id: str, col: int, row: int) -> dict:
        session = self._sm.get_session(session_id)
        session.katrain("play", coords=(col, row))
        return {"status": "ok"}

    def _local_pass(self, session_id: str) -> dict:
        session = self._sm.get_session(session_id)
        session.katrain("play", coords=None)
        return {"status": "ok"}

    def _local_resign(self, session_id: str) -> dict:
        session = self._sm.get_session(session_id)
        session.katrain("resign")
        return {"status": "ok"}

    # --- Broadcast helpers ---

    def _broadcast_pending(self, session_id: str, col: int, row: int) -> None:
        self._sm.broadcast_to_session(session_id, {"type": "platform_move_pending", "col": col, "row": row})

    def _broadcast_confirmed(self, session_id: str, col: int, row: int, move_number: int) -> None:
        self._sm.broadcast_to_session(
            session_id, {"type": "platform_move_confirmed", "col": col, "row": row, "move_number": move_number}
        )

    def _broadcast_rejected(self, session_id: str, reason: str) -> None:
        self._sm.broadcast_to_session(session_id, {"type": "platform_move_rejected", "reason": reason})
