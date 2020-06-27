import pytest

from katrain.core.game import Game, IllegalMoveException, Move
from katrain.core.base_katrain import KaTrainBase, OUTPUT_INFO
from katrain.core.game_node import GameNode


class MockKaTrain(KaTrainBase):
    pass


class MockEngine:
    def request_analysis(self, *args, **kwargs):
        pass


@pytest.fixture
def new_game():
    return GameNode(properties={"SZ": 19})


class TestBoard:
    def nonempty_chains(self, b):
        return [c for c in b.chains if c]

    def test_merge(self, new_game):
        b = Game(MockKaTrain(force_package_config=True), MockEngine(), move_tree=new_game)
        b.play(Move.from_gtp("B9", player="B"))
        b.play(Move.from_gtp("A3", player="B"))
        b.play(Move.from_gtp("A9", player="B"))
        assert 2 == len(self.nonempty_chains(b))
        assert 3 == len(b.stones)
        assert 0 == len(b.prisoners)

    def test_collide(self, new_game):
        b = Game(MockKaTrain(force_package_config=True), MockEngine(), move_tree=new_game)
        b.play(Move.from_gtp("B9", player="B"))
        with pytest.raises(IllegalMoveException):
            b.play(Move.from_gtp("B9", player="W"))
        assert 1 == len(self.nonempty_chains(b))
        assert 1 == len(b.stones)
        assert 0 == len(b.prisoners)

    def test_capture(self, new_game):
        b = Game(MockKaTrain(force_package_config=True), MockEngine(), move_tree=new_game)
        b.play(Move.from_gtp("A2", player="B"))
        b.play(Move.from_gtp("B1", player="W"))
        b.play(Move.from_gtp("A1", player="W"))
        b.play(Move.from_gtp("C1", player="B"))
        assert 3 == len(self.nonempty_chains(b))
        assert 4 == len(b.stones)
        assert 0 == len(b.prisoners)
        b.play(Move.from_gtp("B2", player="B"))
        assert 2 == len(self.nonempty_chains(b))
        assert 3 == len(b.stones)
        assert 2 == len(b.prisoners)
        b.play(Move.from_gtp("B1", player="B"))
        with pytest.raises(IllegalMoveException) as exc:
            b.play(Move.from_gtp("A1", player="W"))
        assert "Suicide" in str(exc.value)
        assert 1 == len(self.nonempty_chains(b))
        assert 4 == len(b.stones)
        assert 2 == len(b.prisoners)

    def test_snapback(self, new_game):
        b = Game(MockKaTrain(force_package_config=True), MockEngine(), move_tree=new_game)
        for move in ["C1", "D1", "E1", "C2", "D3", "E4", "F2", "F3", "F4"]:
            b.play(Move.from_gtp(move, player="B"))
        for move in ["D2", "E2", "C3", "D4", "C4"]:
            b.play(Move.from_gtp(move, player="W"))
        assert 5 == len(self.nonempty_chains(b))
        assert 14 == len(b.stones)
        assert 0 == len(b.prisoners)
        b.play(Move.from_gtp("E3", player="W"))
        assert 4 == len(self.nonempty_chains(b))
        assert 14 == len(b.stones)
        assert 1 == len(b.prisoners)
        b.play(Move.from_gtp("D3", player="B"))
        assert 4 == len(self.nonempty_chains(b))
        assert 12 == len(b.stones)
        assert 4 == len(b.prisoners)

    def test_ko(self, new_game):
        b = Game(MockKaTrain(force_package_config=True), MockEngine(), move_tree=new_game)
        for move in ["A2", "B1"]:
            b.play(Move.from_gtp(move, player="B"))

        for move in ["B2", "C1"]:
            b.play(Move.from_gtp(move, player="W"))
        b.play(Move.from_gtp("A1", player="W"))
        assert 4 == len(self.nonempty_chains(b))
        assert 4 == len(b.stones)
        assert 1 == len(b.prisoners)
        with pytest.raises(IllegalMoveException) as exc:
            b.play(Move.from_gtp("B1", player="B"))
        assert "Ko" in str(exc.value)

        b.play(Move.from_gtp("B1", player="B"), ignore_ko=True)
        assert 2 == len(b.prisoners)

        with pytest.raises(IllegalMoveException) as exc:
            b.play(Move.from_gtp("A1", player="W"))

        b.play(Move.from_gtp("F1", player="W"))
        b.play(Move(coords=None, player="B"))
        b.play(Move.from_gtp("A1", player="W"))
        assert 3 == len(b.prisoners)
