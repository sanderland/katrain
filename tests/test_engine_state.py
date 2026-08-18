"""Regression tests for engine error handling and shared-state locking."""

import queue
import threading

import pytest

from katrain.core.base_katrain import KaTrainBase
from katrain.core.engine import BaseEngine, KataGoEngine
from katrain.core.game import Game, IllegalMoveException, Move
from katrain.core.game_node import GameNode


class MockKaTrain(KaTrainBase):
    pass


class MockEngine:
    def request_analysis(self, *args, **kwargs):
        pass


class StubEngine(KataGoEngine):
    """A KataGoEngine with the bookkeeping set up but no subprocess."""

    def __init__(self, katrain):
        BaseEngine.__init__(self, katrain, {})
        self.allow_recovery = False
        self.queries = {}
        self.ponder_query = None
        self.query_counter = 0
        self.katago_process = None
        self.base_priority = 0
        self.write_queue = queue.Queue()
        self.thread_lock = threading.RLock()
        self.analysis_thread = self.stderr_thread = self.write_stdin_thread = None


@pytest.fixture
def katrain():
    return MockKaTrain(force_package_config=True, debug_level=0)


class TestEngineErrors:
    def test_base_on_error_accepts_shared_call_signature(self, katrain):
        """get_engine_path calls on_error(message, code); subclasses that do not
        override it (KataGoContributeEngine) must not hit a TypeError."""
        engine = BaseEngine(katrain, {})
        engine.on_error("some message", "SOME-CODE")  # must not raise

    def test_missing_exe_reports_error_and_returns_none(self, katrain):
        engine = BaseEngine(katrain, {})
        errors = []
        engine.on_error = lambda message, code=None, allow_popup=True: errors.append((message, code))
        assert engine.get_engine_path("/nonexistent/dir/katago-does-not-exist") is None
        assert errors and errors[0][1] == "KATAGO-EXE"


class TestEngineSharedState:
    def test_on_new_game_clears_queries_in_place(self, katrain):
        """Threads hold a reference to these objects; rebinding orphans their view."""
        engine = StubEngine(katrain)
        engine.queries["QUERY:1"] = (None, None, 0.0, None, None)
        queries, write_queue = engine.queries, engine.write_queue
        engine.write_queue.put(({"id": "PENDING"}, None, None, None, None))

        engine.on_new_game()

        assert engine.queries is queries
        assert engine.write_queue is write_queue
        assert not engine.queries
        # the pending analysis is dropped; only the terminate for QUERY:1 stays queued
        queued = []
        while not engine.write_queue.empty():
            queued.append(engine.write_queue.get_nowait()[0])
        assert [{"action": "terminate", "terminateId": "QUERY:1"}] == queued

    def test_restart_clears_queries_in_place(self, katrain):
        engine = StubEngine(katrain)
        engine.queries["QUERY:1"] = (None, None, 0.0, None, None)
        queries = engine.queries
        engine.start = lambda: None  # no subprocess
        engine.restart()
        assert engine.queries is queries and not engine.queries

    def test_terminate_queries_is_reentrant(self, katrain):
        """terminate_queries -> terminate_query both take thread_lock."""
        engine = StubEngine(katrain)
        node = object()
        engine.queries["QUERY:1"] = (None, None, 0.0, None, node)

        done = threading.Event()
        threading.Thread(target=lambda: (engine.terminate_queries(), done.set()), daemon=True).start()
        assert done.wait(timeout=5), "terminate_queries deadlocked"
        assert "QUERY:1" not in engine.queries

    def test_stop_pondering_is_reentrant_under_lock(self, katrain):
        """_write_stdin_thread calls stop_pondering while already holding the lock."""
        engine = StubEngine(katrain)
        engine.ponder_query = {"id": "QUERY:7"}

        done = threading.Event()

        def call_under_lock():
            with engine.thread_lock:
                engine.stop_pondering()
            done.set()

        threading.Thread(target=call_under_lock, daemon=True).start()
        assert done.wait(timeout=5), "stop_pondering deadlocked"
        assert engine.ponder_query is None

    def test_is_idle_and_queries_remaining(self, katrain):
        engine = StubEngine(katrain)
        assert engine.is_idle() and engine.queries_remaining() == 0
        engine.queries["QUERY:1"] = (None, None, 0.0, None, None)
        assert not engine.is_idle() and engine.queries_remaining() == 1


class TestGameLocking:
    def test_play_is_reentrant_on_illegal_move(self, katrain):
        """play() holds the lock and re-enters _calculate_groups to roll back."""
        game = Game(katrain, MockEngine(), move_tree=GameNode(properties={"SZ": 19}))
        game.play(Move.from_gtp("D4", player="B"))
        with pytest.raises(IllegalMoveException):
            game.play(Move.from_gtp("D4", player="W"))
        assert 1 == len(game.stones)
        assert 1 == game.current_node.depth

    def test_concurrent_play_and_navigation_keeps_board_consistent(self, katrain):
        """AI moves are generated off-thread while the UI thread navigates."""
        game = Game(katrain, MockEngine(), move_tree=GameNode(properties={"SZ": 19}))
        coords = [f"{c}{r}" for c in "ABCDEFGH" for r in range(1, 9)]
        errors = []

        def play_moves():
            try:
                for i, gtp in enumerate(coords):
                    game.play(Move.from_gtp(gtp, player="BW"[i % 2]))
            except Exception as e:  # noqa: BLE001 - reported below
                errors.append(e)

        def navigate():
            try:
                for _ in range(200):
                    game.set_current_node(game.current_node)
                    len(game.stones)
                    game.prisoner_count
            except Exception as e:  # noqa: BLE001 - reported below
                errors.append(e)

        threads = [threading.Thread(target=play_moves), threading.Thread(target=navigate)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert not any(t.is_alive() for t in threads), "board operations deadlocked"
        assert not errors, errors
        # every stone on the board is accounted for by exactly one chain
        assert len(coords) == len(game.stones)
