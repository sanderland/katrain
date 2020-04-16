import pytest
from unittest.mock import MagicMock

from game import Game, IllegalMoveException, Move


class MockKaTrain:
    def log(self, msg, lvl):
        pass


class MockEngine:
    def request_analysis(self, *args, **kwargs):
        pass


class TestBoard:
    def nonempty_chains(self, b):
        return [c for c in b.chains if c]

    def test_merge(self):
        b = Game(MockKaTrain(), MockEngine(), {}, board_size=9)
        b.play(Move.from_gtp("B9", player=0))
        b.play(Move.from_gtp("A3", player=0))
        b.play(Move.from_gtp("A9", player=0))
        assert 2 == len(self.nonempty_chains(b))
        assert 3 == len(b.stones)
        assert 0 == len(b.prisoners)

    def test_collide(self):
        b = Game(MockKaTrain(), MockEngine(), {}, board_size=9)
        b.play(Move.from_gtp("B9", player=0))
        with pytest.raises(IllegalMoveException):
            b.play(Move.from_gtp("B9", player=1))
        assert 1 == len(self.nonempty_chains(b))
        assert 1 == len(b.stones)
        assert 0 == len(b.prisoners)

    def test_capture(self):
        b = Game(MockKaTrain(), MockEngine(), {}, board_size=9)
        b.play(Move.from_gtp("A2", player=0))
        b.play(Move.from_gtp("B1", player=1))
        b.play(Move.from_gtp("A1", player=1))
        b.play(Move.from_gtp("C1", player=0))
        assert 3 == len(self.nonempty_chains(b))
        assert 4 == len(b.stones)
        assert 0 == len(b.prisoners)
        b.play(Move.from_gtp("B2", player=0))
        assert 2 == len(self.nonempty_chains(b))
        assert 3 == len(b.stones)
        assert 2 == len(b.prisoners)
        b.play(Move.from_gtp("B1", player=0))
        with pytest.raises(IllegalMoveException) as exc:
            b.play(Move.from_gtp("A1", player=1))
        assert "Suicide" in str(exc.value)
        assert 1 == len(self.nonempty_chains(b))
        assert 4 == len(b.stones)
        assert 2 == len(b.prisoners)

    def test_snapback(self):
        b = Game(MockKaTrain(), MockEngine(), {}, board_size=9)
        for move in ["C1", "D1", "E1", "C2", "D3", "E4", "F2", "F3", "F4"]:
            b.play(Move.from_gtp(move, player=0))
        for move in ["D2", "E2", "C3", "D4", "C4"]:
            b.play(Move.from_gtp(move, player=1))
        assert 5 == len(self.nonempty_chains(b))
        assert 14 == len(b.stones)
        assert 0 == len(b.prisoners)
        b.play(Move.from_gtp("E3", player=1))
        assert 4 == len(self.nonempty_chains(b))
        assert 14 == len(b.stones)
        assert 1 == len(b.prisoners)
        b.play(Move.from_gtp("D3", player=0))
        assert 4 == len(self.nonempty_chains(b))
        assert 12 == len(b.stones)
        assert 4 == len(b.prisoners)

    def test_ko(self):
        b = Game(MockKaTrain(), MockEngine(), {}, board_size=9)
        for move in ["A2", "B1"]:
            b.play(Move.from_gtp(move, player=0))

        for move in ["B2", "C1"]:
            b.play(Move.from_gtp(move, player=1))
        b.play(Move.from_gtp("A1", player=1))
        assert 4 == len(self.nonempty_chains(b))
        assert 4 == len(b.stones)
        assert 1 == len(b.prisoners)
        with pytest.raises(IllegalMoveException) as exc:
            b.play(Move.from_gtp("B1", player=0))
        assert "Ko" in str(exc.value)

        b.play(Move.from_gtp("B1", player=0), ignore_ko=True)
        assert 2 == len(b.prisoners)

        with pytest.raises(IllegalMoveException) as exc:
            b.play(Move.from_gtp("A1", player=1))

        b.play(Move.from_gtp("F1", player=1))
        b.play(Move(coords=(None, None), player=0))
        b.play(Move.from_gtp("A1", player=1))
        assert 3 == len(b.prisoners)
