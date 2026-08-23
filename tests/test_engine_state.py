"""Regression tests for engine error handling and shared-state locking."""

import queue
import threading
import time

import pytest

from katrain.core.ai import STRATEGY_REGISTRY, AIStrategy, AnalysisDiscardedException, generate_ai_move
from katrain.core.base_katrain import KaTrainBase
from katrain.core.engine import BaseEngine, KataGoEngine
from katrain.core.game import BaseGame, Game, IllegalMoveException, Move
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
        self.query_generation = 0
        self.write_queue = queue.Queue()
        self.thread_lock = threading.RLock()
        self.analysis_thread = self.stderr_thread = self.write_stdin_thread = None


@pytest.fixture
def katrain():
    return MockKaTrain(force_package_config=True, debug_level=0)


class TestEngineErrors:
    def test_base_on_error_accepts_shared_call_signature(self, katrain):
        engine = BaseEngine(katrain, {})
        engine.on_error("some message", "SOME-CODE")

    def test_missing_exe_reports_error_and_returns_none(self, katrain):
        engine = BaseEngine(katrain, {})
        errors = []
        engine.on_error = lambda message, code=None, allow_popup=True: errors.append((message, code))
        assert engine.get_engine_path("/nonexistent/dir/katago-does-not-exist") is None
        assert errors and errors[0][1] == "KATAGO-EXE"

    def test_bundled_macos_exe_used_on_apple_silicon(self, katrain, monkeypatch, tmp_path):
        bundled = tmp_path / "katago-osx"
        bundled.write_bytes(b"")

        import katrain.core.engine as engine_module

        monkeypatch.setattr(engine_module, "kivy_platform", "macosx")
        monkeypatch.setattr(engine_module, "find_package_resource", lambda path: str(bundled))

        engine = BaseEngine(katrain, {})
        assert engine.get_engine_path("") == str(bundled)


class TestEngineSharedState:
    def test_on_new_game_clears_queries_in_place(self, katrain):
        engine = StubEngine(katrain)
        engine.queries["QUERY:1"] = (None, None, 0.0, None, None)
        queries, write_queue = engine.queries, engine.write_queue
        engine.write_queue.put(({"id": "PENDING"}, None, None, None, None, engine.query_generation))

        engine.on_new_game()

        assert engine.queries is queries
        assert engine.write_queue is write_queue
        assert not engine.queries
        queued = []
        while not engine.write_queue.empty():
            queued.append(engine.write_queue.get_nowait()[0])
        assert [{"action": "terminate", "terminateId": "QUERY:1"}] == queued

    def test_restart_clears_queries_in_place(self, katrain):
        engine = StubEngine(katrain)
        engine.queries["QUERY:1"] = (None, None, 0.0, None, None)
        queries = engine.queries
        engine.start = lambda: None
        engine.restart()
        assert engine.queries is queries and not engine.queries

    def test_terminate_queries_is_reentrant(self, katrain):
        engine = StubEngine(katrain)
        node = object()
        engine.queries["QUERY:1"] = (None, None, 0.0, None, node)

        done = threading.Event()
        threading.Thread(target=lambda: (engine.terminate_queries(), done.set()), daemon=True).start()
        assert done.wait(timeout=5), "terminate_queries deadlocked"
        assert "QUERY:1" not in engine.queries

    def test_stop_pondering_is_reentrant_under_lock(self, katrain):
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
        game = Game(katrain, MockEngine(), move_tree=GameNode(properties={"SZ": 19}))
        game.play(Move.from_gtp("D4", player="B"))
        with pytest.raises(IllegalMoveException):
            game.play(Move.from_gtp("D4", player="W"))
        assert 1 == len(game.stones)
        assert 1 == game.current_node.depth

    def test_concurrent_play_and_navigation_keeps_board_consistent(self, katrain):
        game = Game(katrain, MockEngine(), move_tree=GameNode(properties={"SZ": 19}))
        coords = [f"{c}{r}" for c in "ABCDEFGH" for r in range(1, 9)]
        errors = []

        def play_moves():
            try:
                for i, gtp in enumerate(coords):
                    game.play(Move.from_gtp(gtp, player="BW"[i % 2]))
            except Exception as e:
                errors.append(e)

        def navigate():
            try:
                for _ in range(200):
                    game.set_current_node(game.current_node)
                    len(game.stones)
                    game.prisoner_count
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=play_moves), threading.Thread(target=navigate)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert not any(t.is_alive() for t in threads), "board operations deadlocked"
        assert not errors, errors
        expected = BaseGame(katrain, move_tree=game.root)
        expected.set_current_node(game.current_node)
        assert set(expected.stones) == set(game.stones)


class FakeNode:
    """Just the bits of GameNode that the AI wait loops read."""

    def __init__(self):
        self.analysis_complete = False
        self.player = "B"
        self.next_player = "W"


class FakeGame:
    def __init__(self, katrain, engine, node):
        self.katrain = katrain
        self.engines = {"B": engine, "W": engine}
        self.current_node = node


class WaitingStrategy(AIStrategy):
    def generate_move(self):
        self.wait_for_analysis()
        return Move.from_gtp("D4", player="B"), "analysis arrived"


class TestDiscardedAnalysis:
    """A discarded query never calls back, so waiting on one has to end by itself."""

    def strategy(self, katrain):
        engine = StubEngine(katrain)
        return engine, WaitingStrategy(FakeGame(katrain, engine, FakeNode()), {})

    def test_wait_for_analysis_aborts_after_new_game(self, katrain):
        engine, strategy = self.strategy(katrain)
        engine.on_new_game()  # bumps query_generation, discarding outstanding work
        with pytest.raises(AnalysisDiscardedException):
            strategy.wait_for_analysis()

    def test_wait_for_analysis_aborts_after_restart(self, katrain):
        engine, strategy = self.strategy(katrain)
        engine.start = lambda: None
        engine.restart()
        with pytest.raises(AnalysisDiscardedException):
            strategy.wait_for_analysis()

    def test_wait_for_analysis_does_not_abort_while_the_query_still_stands(self, katrain):
        _engine, strategy = self.strategy(katrain)
        node = strategy.cn

        def complete_analysis():
            time.sleep(0.05)
            node.analysis_complete = True

        threading.Thread(target=complete_analysis, daemon=True).start()
        done = threading.Event()
        threading.Thread(target=lambda: (strategy.wait_for_analysis(), done.set()), daemon=True).start()
        assert done.wait(timeout=5), "wait_for_analysis did not return once the analysis completed"

    def test_generate_ai_move_gives_up_instead_of_raising(self, katrain, monkeypatch):
        """The discard lands while the move is being generated -- the interleaving that used to wedge."""
        engine, strategy = self.strategy(katrain)
        monkeypatch.setitem(STRATEGY_REGISTRY, "test:waiting", WaitingStrategy)

        result = []
        done = threading.Event()
        threading.Thread(
            target=lambda: (result.append(generate_ai_move(strategy.game, "test:waiting", {})), done.set()),
            daemon=True,
        ).start()
        time.sleep(0.05)  # let it reach the wait loop
        engine.on_new_game()

        assert done.wait(timeout=5), "generate_ai_move kept waiting for analysis that was discarded"
        assert [(None, None)] == result
