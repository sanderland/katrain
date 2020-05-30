import pytest

from katrain.core.constants import AI_STRATEGIES_RECOMMENDED_ORDER, AI_STRATEGIES


class TestAI:
    def test_order(self):
        assert set(AI_STRATEGIES_RECOMMENDED_ORDER) == set(AI_STRATEGIES)
