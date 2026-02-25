import os
import shutil

import pytest

from katrain.core.ai import ai_rank_estimation, generate_ai_move
from katrain.core.base_katrain import KaTrainBase
from katrain.core.constants import AI_DEFAULT, AI_HUMAN
from katrain.core.engine import KataGoEngine
from katrain.core.game import Game, KaTrainSGF
from katrain.core.utils import find_package_resource


def test_sgf_roundtrip_preserves_moves():
    sgf = "(;GM[1]FF[4]CA[UTF-8]SZ[19]KM[6.5];B[pd];W[dd];B[qp])"
    root = KaTrainSGF.parse_sgf(sgf)
    out = root.sgf()
    root2 = KaTrainSGF.parse_sgf(out)

    def main_branch_moves(r):
        n = r
        moves = []
        while n.children:
            n = n.children[0]
            if n.move:
                moves.append(n.move.gtp())
        return moves

    assert main_branch_moves(root2) == main_branch_moves(root)


def test_ai_rank_estimation_v2_contract():
    katrain = KaTrainBase(force_package_config=True, debug_level=0)

    assert ai_rank_estimation(AI_DEFAULT, katrain.config(f"ai/{AI_DEFAULT}")) == 9

    human_settings = dict(katrain.config(f"ai/{AI_HUMAN}"))
    assert ai_rank_estimation(AI_HUMAN, human_settings) == 1 - round(human_settings["human_kyu_rank"])

    human_settings["profile"] = "proyear"
    assert ai_rank_estimation(AI_HUMAN, human_settings) is None


@pytest.mark.skipif(os.environ.get("CI", "").lower() == "true", reason="CI environment doesn't provide KataGo/OpenCL")
def test_generate_ai_move_default_smoke():
    if shutil.which("katago") is None:
        pytest.skip("katago binary not found in PATH")

    katrain = KaTrainBase(force_package_config=True, debug_level=0)
    engine = KataGoEngine(katrain, katrain.config("engine"))
    if engine.katago_process is None:
        pytest.skip("KataGoEngine failed to start")

    try:
        game = Game(katrain, engine, analyze_fast=True)
        move, played_node = generate_ai_move(game, AI_DEFAULT, katrain.config(f"ai/{AI_DEFAULT}") or {})
        assert not move.is_pass
        assert played_node == game.current_node
        assert game.current_node.depth == 1
    finally:
        engine.shutdown(finish=False)


@pytest.mark.humansl
@pytest.mark.skipif(os.environ.get("CI", "").lower() == "true", reason="CI environment doesn't provide KataGo/OpenCL")
def test_generate_ai_move_humansl_smoke():
    if shutil.which("katago") is None:
        pytest.skip("katago binary not found in PATH")

    katrain = KaTrainBase(force_package_config=True, debug_level=0)
    human_model_cfg = katrain.config("engine/humanlike_model", "")
    if not human_model_cfg:
        pytest.skip("No HumanSL model configured (engine/humanlike_model is empty)")

    human_model_path = find_package_resource(human_model_cfg)
    if not os.path.isfile(human_model_path):
        pytest.skip(f"HumanSL model not found at {human_model_path}")

    engine = KataGoEngine(katrain, katrain.config("engine"))
    if engine.katago_process is None:
        pytest.skip("KataGoEngine failed to start")

    try:
        game = Game(katrain, engine, analyze_fast=True)
        move, played_node = generate_ai_move(game, AI_HUMAN, katrain.config(f"ai/{AI_HUMAN}") or {})
        assert not move.is_pass
        assert played_node == game.current_node
        assert played_node.ai_thoughts.startswith("HumanSL(")
    finally:
        engine.shutdown(finish=False)
