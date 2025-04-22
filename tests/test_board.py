import pytest

from katrain.core.base_katrain import KaTrainBase
from katrain.core.engine import BaseEngine
from katrain.core.game import Game, IllegalMoveException, Move, KaTrainSGF
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
        with pytest.raises(IllegalMoveException, match="Single stone suicide"):
            b.play(Move.from_gtp("A1", player="W"))
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

    def test_handicap_load(self):
        input_sgf = (
            "(;GM[1]FF[4]CA[UTF-8]AP[CGoban:3]ST[2]RU[Chinese]SZ[19]HA[2]KM[0.50]TM[600]OT[5x30 byo-yomi]PW[kneh]PB[ayabot003]WR[4k]BR[6k]DT[2021-01-04]PC[The KGS Go Server at http://www.gokgs.com/]C[ayabot003 [6k\\"
            "]: GTP Engine for ayabot003 (black): Aya version 7.85x]RE[W+Resign];B[pd]BL[599.647];B[dp]BL[599.477];W[pp]WL[597.432];B[cd]BL[598.896];W[ed]WL[595.78];B[ec]BL[598.558])"
        )
        root = KaTrainSGF.parse_sgf(input_sgf)
        game = Game(MockKaTrain(force_package_config=True), MockEngine(), move_tree=root)
        assert 0 == len(game.root.placements)

        root2 = KaTrainSGF.parse_sgf("(;GM[1]FF[4]SZ[19]HA[2];)")
        game2 = Game(MockKaTrain(force_package_config=True), MockEngine(), move_tree=root2)
        assert 2 == len(game2.root.placements)

    def test_suicide(self):
        rulesets_to_test = BaseEngine.RULESETS_ABBR + [('{"suicide":true}', ""), ('{"suicide":false}', "")]
        for shortrule, _ in rulesets_to_test:
            new_game = GameNode(properties={"SZ": 19, "RU": shortrule})
            b = Game(MockKaTrain(force_package_config=True), MockEngine(), move_tree=new_game)
            b.play(Move.from_gtp("A18", player="B"))
            b.play(Move.from_gtp("B18", player="B"))
            b.play(Move.from_gtp("C19", player="B"))
            b.play(Move.from_gtp("A19", player="W"))
            assert 4 == len(b.stones)
            assert 0 == len(b.prisoners)

            if shortrule in ["tt", "nz", '{"suicide":true}']:
                b.play(Move.from_gtp("B19", player="W"))
                assert 3 == len(b.stones)
                assert 2 == len(b.prisoners)
            else:
                with pytest.raises(IllegalMoveException, match="Suicide"):
                    b.play(Move.from_gtp("B19", player="W"))
                assert 4 == len(b.stones)
                assert 0 == len(b.prisoners)
