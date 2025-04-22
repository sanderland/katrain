import os

import pytest

from katrain.core.ai import ai_rank_estimation, generate_ai_move
from katrain.core.base_katrain import KaTrainBase
from katrain.core.constants import AI_STRATEGIES, AI_STRATEGIES_RECOMMENDED_ORDER, OUTPUT_INFO
from katrain.core.engine import KataGoEngine
from katrain.core.game import Game


class TestAI:
    def test_order(self):
        assert set(AI_STRATEGIES_RECOMMENDED_ORDER) == set(AI_STRATEGIES)

    @pytest.mark.skipif(os.environ.get("CI", "").lower() == "true", reason="GH actions has no OpenCL")
    def test_ai_strategies(self):
        katrain = KaTrainBase(force_package_config=True, debug_level=0)
        engine = KataGoEngine(katrain, katrain.config("engine"))

        game = Game(katrain, engine)
        n_rounds = 3
        for _ in range(n_rounds):
            for strategy in AI_STRATEGIES:
                settings = katrain.config(f"ai/{strategy}")
                move, played_node = generate_ai_move(game, strategy, settings)
                katrain.log(f"Testing strategy {strategy} -> {move}", OUTPUT_INFO)
                assert move.coords is not None
                assert played_node == game.current_node

        assert game.current_node.depth == len(AI_STRATEGIES) * n_rounds

        for strategy in AI_STRATEGIES:
            game = Game(katrain, engine)
            settings = katrain.config(f"ai/{strategy}")
            move, played_node = generate_ai_move(game, strategy, settings)
            katrain.log(f"Testing strategy on first move {strategy} -> {move}", OUTPUT_INFO)
            assert game.current_node.depth == 1

    def test_ai_rank_estimation(self):
        katrain = KaTrainBase(force_package_config=True, debug_level=0)
        for strategy in AI_STRATEGIES:
            settings = katrain.config(f"ai/{strategy}")
            rank = ai_rank_estimation(strategy, settings)
            assert -20 <= rank <= 9
