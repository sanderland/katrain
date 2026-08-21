"""KaTrain's side of the pysgf integration.

The parser itself lives in pysgf and is tested there; what is worth testing here
is that KaTrain's GameNode subclass propagates through it, plus the two malformed
GIB regressions pysgf has not adopted yet.
"""

import os
import re
from unittest.mock import MagicMock

from pysgf import Move

from katrain.core.base_katrain import KaTrainBase
from katrain.core.game import Game, KaTrainSGF
from katrain.core.game_node import GameNode


def test_parsing_produces_katrain_nodes():
    root = KaTrainSGF.parse_sgf("(;GM[1]FF[4]SZ[19]AB[dd][dj];B[dp];W[pp](;B[pj])(;B[pd]))")
    assert isinstance(root, GameNode)
    assert all(isinstance(n, GameNode) for n in root.nodes_in_tree)
    assert isinstance(root.play(Move.from_gtp("Q16")), GameNode)
    assert [Move.from_sgf("dd", (19, 19)), Move.from_sgf("dj", (19, 19))] == root.placements


def test_foxwq():
    for sgf in ["data/fox sgf error.sgf", "data/fox sgf works.sgf"]:
        file = os.path.join(os.path.dirname(__file__), sgf)
        move_tree = KaTrainSGF.parse_file(file)
        katrain = KaTrainBase(force_package_config=True, debug_level=0)
        game = Game(katrain, MagicMock(), move_tree)

        assert [] == move_tree.placements
        assert [] == game.root.placements
        while game.current_node.children:
            assert 1 == len(game.current_node.children)
            game.redo(1)


def test_gib_malformed_ini_line():
    file = os.path.join(os.path.dirname(__file__), "data/test.gib")
    with open(file, encoding="utf-8", errors="ignore") as f:
        gib = f.read()

    for broken in ["INI 0 1", "INI 0 1 0 x", "INI"]:
        mangled = re.sub(r"^INI .*$", broken, gib, flags=re.MULTILINE)
        root = KaTrainSGF.parse_gib(mangled)
        assert "pd" == root.children[0].get_property("B")


def test_gib_malformed_metadata_lines():
    gib = "\n".join(
        [
            "\\[GAMEBLACKNAME=kim (2D)\\]",
            "\\[GAMEWHITENAME=wildsim1 (2D)\\]",
            "\\[GAMEINFOMAIN=GRLT:0,ZIPSU:x,GONGJE:oops,\\]",
            "\\[GAMETAG=Cxxxx:yy:zz,W:nope,G:nope,\\]",
            "STO 0 1 1 15 3",
        ]
    )
    root = KaTrainSGF.parse_gib(gib)
    assert "kim" == root.get_property("PB")
    assert root.get_property("KM") is None
    assert root.get_property("DT") is None
