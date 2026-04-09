"""Contract tests: verify all PlatformAdapter subclasses implement the interface correctly."""

import inspect

import pytest

from katrain.web.platforms.base import PlatformAdapter
from katrain.web.platforms.ogs.adapter import OGSAdapter
from katrain.web.platforms.fox.adapter import FoxAdapter
from katrain.web.platforms.golaxy.adapter import GolaxyAdapter


ALL_ADAPTERS = [OGSAdapter, FoxAdapter, GolaxyAdapter]


@pytest.fixture(params=ALL_ADAPTERS, ids=lambda cls: cls.__name__)
def adapter_cls(request):
    return request.param


class TestAdapterContract:
    def test_is_platform_adapter(self, adapter_cls):
        assert issubclass(adapter_cls, PlatformAdapter)

    def test_has_platform_name(self, adapter_cls):
        adapter = adapter_cls()
        assert isinstance(adapter.platform_name, str)
        assert len(adapter.platform_name) > 0

    def test_has_supported_board_sizes(self, adapter_cls):
        adapter = adapter_cls()
        assert isinstance(adapter.supported_board_sizes, list)
        assert 19 in adapter.supported_board_sizes

    def test_capability_flags_are_bool(self, adapter_cls):
        adapter = adapter_cls()
        for flag in [
            "supports_live_play",
            "supports_scoring",
            "supports_automatch",
            "supports_rooms",
            "supports_seek_graph",
        ]:
            assert isinstance(getattr(adapter, flag), bool), f"{flag} should be bool"

    def test_starts_disconnected(self, adapter_cls):
        adapter = adapter_cls()
        assert adapter.is_connected is False

    def test_has_abstract_methods(self, adapter_cls):
        """Verify the adapter implements all abstract methods (connect, disconnect, submit_move, etc.)."""
        adapter = adapter_cls()
        # These should not raise NotImplementedError when called (they're implemented)
        for method_name in ["connect", "disconnect", "submit_move", "submit_pass", "resign"]:
            method = getattr(adapter, method_name)
            assert callable(method), f"{method_name} should be callable"
            assert inspect.iscoroutinefunction(method), f"{method_name} should be async"

    def test_callback_registration(self, adapter_cls):
        """All callback registration methods should work without error."""
        adapter = adapter_cls()

        async def dummy(*args):
            pass

        adapter.on_opponent_move(dummy)
        adapter.on_clock_update(dummy)
        adapter.on_challenge_received(dummy)
        adapter.on_game_started(dummy)
        adapter.on_game_ended(dummy)
        adapter.on_game_phase_changed(dummy)
        adapter.on_automatch_found(dummy)
        adapter.on_connection_lost(dummy)
        adapter.on_reconnected(dummy)
        adapter.on_auth_expired(dummy)
        adapter.on_token_refreshed(dummy)

    def test_unique_platform_names(self):
        """Each adapter must have a unique platform_name."""
        names = [cls().platform_name for cls in ALL_ADAPTERS]
        assert len(names) == len(set(names)), f"Duplicate platform names: {names}"


class TestOGSSpecific:
    def test_ogs_capabilities(self):
        adapter = OGSAdapter()
        assert adapter.supports_live_play is True
        assert adapter.supports_scoring is True
        assert adapter.supports_automatch is True
        assert adapter.supports_rooms is False
        assert adapter.supports_seek_graph is True

    def test_ogs_rank_parsing(self):
        from katrain.web.platforms.ogs.adapter import _parse_rank

        # 30k = ranking 0
        assert _parse_rank(0)[0] == "30k"
        # 1k = ranking 29
        assert _parse_rank(29)[0] == "1k"
        # 1d = ranking 30
        assert _parse_rank(30)[0] == "1d"
        # 9d = ranking 38
        assert _parse_rank(38)[0] == "9d"
        # 5k = ranking 25
        assert _parse_rank(25)[0] == "5k"

    def test_ogs_time_control_parsing(self):
        from katrain.web.platforms.ogs.adapter import _parse_time_control

        tc = _parse_time_control({
            "system": "byoyomi",
            "main_time": 600,
            "period_time": 30,
            "periods": 5,
        })
        assert tc.system == "byoyomi"
        assert tc.main_time == 600
        assert tc.period_time == 30
        assert tc.periods == 5

    def test_ogs_clock_parsing(self):
        from katrain.web.platforms.ogs.adapter import _parse_clock

        clock = _parse_clock(
            {
                "current_player": 123,
                "black_player_id": 123,
                "black_time": {"thinking_time": 300},
                "white_time": {"thinking_time": 250},
            },
            "B",
        )
        assert clock.current_player == "B"
        assert clock.black_time == {"thinking_time": 300}
        assert clock.paused is False
