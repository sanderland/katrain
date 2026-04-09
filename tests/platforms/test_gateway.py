"""Gateway state machine tests: pending -> confirmed, pending -> rejected, timeout."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from katrain.web.platforms.gateway import PlatformCommandGateway, PlatformMoveRejectedError
from katrain.web.platforms.manager import PlatformManager
from katrain.web.platforms.models import GamePhase, PlatformGameContext


class MockAdapter:
    platform_name = "mock"
    supports_scoring = False

    async def submit_move(self, game_id, col, row):
        return True

    async def submit_pass(self, game_id):
        return True

    async def resign(self, game_id):
        pass


class MockSession:
    def __init__(self):
        self.moves = []
        self.resigned = False
        self.katrain_calls = []

    def katrain(self, command, coords=None):
        self.katrain_calls.append((command, coords))
        if command == "play":
            self.moves.append(coords)
        elif command == "resign":
            self.resigned = True


class MockSessionManager:
    def __init__(self):
        self.sessions = {}
        self.broadcasts = []

    def get_session(self, session_id):
        if session_id not in self.sessions:
            self.sessions[session_id] = MockSession()
        return self.sessions[session_id]

    def broadcast_to_session(self, session_id, msg):
        self.broadcasts.append((session_id, msg))


@pytest.fixture
def setup():
    sm = MockSessionManager()
    pm = PlatformManager(sm)
    adapter = MockAdapter()
    pm._adapters["mock"] = adapter

    ctx = PlatformGameContext(
        session_id="session-1",
        platform="mock",
        remote_game_id="game-42",
        my_color="B",
    )
    pm._active_games["game-42"] = ctx
    pm._session_to_game["session-1"] = "game-42"

    gateway = PlatformCommandGateway(pm, sm)
    return gateway, pm, sm, adapter, ctx


class TestGatewayPlayMove:
    @pytest.mark.asyncio
    async def test_platform_move_confirmed(self, setup):
        gateway, pm, sm, adapter, ctx = setup
        result = await gateway.play_move("session-1", 3, 3, user_id=1)
        assert result == {"status": "ok"}
        assert ctx.last_confirmed_move == 1
        assert ctx.pending_action is None
        # Should have broadcast pending then confirmed
        types = [msg["type"] for _, msg in sm.broadcasts]
        assert "platform_move_pending" in types
        assert "platform_move_confirmed" in types

    @pytest.mark.asyncio
    async def test_platform_move_rejected(self, setup):
        gateway, pm, sm, adapter, ctx = setup
        adapter.submit_move = AsyncMock(return_value=False)
        with pytest.raises(PlatformMoveRejectedError):
            await gateway.play_move("session-1", 3, 3, user_id=1)
        assert ctx.pending_action is None
        types = [msg["type"] for _, msg in sm.broadcasts]
        assert "platform_move_rejected" in types

    @pytest.mark.asyncio
    async def test_platform_move_exception(self, setup):
        gateway, pm, sm, adapter, ctx = setup
        adapter.submit_move = AsyncMock(side_effect=ConnectionError("network"))
        with pytest.raises(PlatformMoveRejectedError, match="network"):
            await gateway.play_move("session-1", 3, 3, user_id=1)
        assert ctx.pending_action is None

    @pytest.mark.asyncio
    async def test_reject_while_pending(self, setup):
        gateway, pm, sm, adapter, ctx = setup
        ctx.set_pending("move")
        with pytest.raises(PlatformMoveRejectedError, match="pending"):
            await gateway.play_move("session-1", 5, 5, user_id=1)

    @pytest.mark.asyncio
    async def test_local_game_passthrough(self, setup):
        gateway, pm, sm, adapter, ctx = setup
        # For a non-platform session, pass through locally
        result = gateway._local_play("session-1", 3, 3)
        assert result == {"status": "ok"}
        session = sm.get_session("session-1")
        assert (3, 3) in session.moves


class TestGatewayPass:
    @pytest.mark.asyncio
    async def test_pass_confirmed(self, setup):
        gateway, pm, sm, adapter, ctx = setup
        result = await gateway.pass_move("session-1", user_id=1)
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_pass_rejected(self, setup):
        gateway, pm, sm, adapter, ctx = setup
        adapter.submit_pass = AsyncMock(return_value=False)
        with pytest.raises(PlatformMoveRejectedError):
            await gateway.pass_move("session-1", user_id=1)


class TestGatewayResign:
    @pytest.mark.asyncio
    async def test_resign_success(self, setup):
        gateway, pm, sm, adapter, ctx = setup
        result = await gateway.resign("session-1", user_id=1)
        assert result == {"status": "ok"}
        session = sm.get_session("session-1")
        assert session.resigned

    @pytest.mark.asyncio
    async def test_resign_failure(self, setup):
        gateway, pm, sm, adapter, ctx = setup
        adapter.resign = AsyncMock(side_effect=ConnectionError("offline"))
        with pytest.raises(PlatformMoveRejectedError, match="offline"):
            await gateway.resign("session-1", user_id=1)


class TestGameContext:
    def test_pending_state(self):
        ctx = PlatformGameContext(session_id="s", platform="p", remote_game_id="g")
        assert ctx.is_pending is False
        ctx.set_pending("move")
        assert ctx.is_pending is True
        assert ctx.pending_action == "move"
        ctx.clear_pending()
        assert ctx.is_pending is False

    def test_recover_from_snapshot(self):
        ctx = PlatformGameContext(session_id="s", platform="p", remote_game_id="g")
        ctx.set_pending("move")
        ctx.needs_resync = True
        ctx.recover_from_snapshot({"phase": "playing", "move_number": 42})
        assert ctx.game_phase == GamePhase.PLAYING
        assert ctx.last_confirmed_move == 42
        assert ctx.is_pending is False
        assert ctx.needs_resync is False
