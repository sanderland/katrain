from __future__ import annotations

from abc import ABC, abstractmethod
import time

from katrain.core.constants import (
    AI_DEFAULT,
    AI_HUMAN,
    OUTPUT_DEBUG,
    OUTPUT_ERROR,
    PRIORITY_EXTRA_AI_QUERY,
)
from katrain.core.game import Game, GameNode, Move
from katrain.core.utils import weighted_selection_without_replacement

# Decorator pattern for adding classes to the registry.
STRATEGY_REGISTRY: dict[str, type["AIStrategy"]] = {}


def register_strategy(strategy_name: str):
    def decorator(strategy_class: type["AIStrategy"]):
        STRATEGY_REGISTRY[strategy_name] = strategy_class
        return strategy_class

    return decorator


def ai_rank_estimation(strategy: str, settings: dict) -> float | None:
    """Estimate playing strength for UI display.

    Returns a 'dan rank' number where:
    - 1   => 1d
    - 0   => 1k
    - -7  => 8k
    """

    if strategy == AI_DEFAULT:
        return 9

    if strategy == AI_HUMAN:
        try:
            profile = settings["profile"]
        except KeyError:
            # Backwards-compatible inference.
            profile = "proyear" if "pro_year" in settings else "rank"

        if profile == "rank":
            return 1 - round(settings["human_kyu_rank"])

        # Pro-year profiles aren't a rank; show unknown.
        if profile == "proyear":
            return None

        raise ValueError(f"Unknown HumanSL profile mode: {profile!r}")

    raise ValueError(f"Unknown AI strategy: {strategy!r}")


def human_profile_string(settings: dict) -> str:
    """Build KataGo HumanSL profile string from AI settings."""
    try:
        profile = settings["profile"]
    except KeyError:
        profile = "proyear" if "pro_year" in settings else "rank"

    if profile == "rank":
        human_kyu_rank = round(settings["human_kyu_rank"])
        human_style = "rank" if settings["modern_style"] else "preaz"

        if human_kyu_rank <= 0:  # dan ranks
            rank_text = f"{1 - human_kyu_rank}d"
        else:  # kyu ranks
            rank_text = f"{human_kyu_rank}k"

        return f"{human_style}_{rank_text}"

    if profile == "proyear":
        pro_year = round(settings["pro_year"])
        return f"proyear_{pro_year}"

    raise ValueError(f"Unknown HumanSL profile mode: {profile!r}")


class AIStrategy(ABC):
    """Base strategy class for AI move generation."""

    def __init__(self, game: Game, ai_settings: dict):
        self.game = game
        self.settings = ai_settings
        self.cn = game.current_node
        self.strategy_name = self.__class__.__name__

    @abstractmethod
    def generate_move(self) -> tuple[Move, str]:
        raise NotImplementedError

    def wait_for_analysis(self) -> None:
        while not self.cn.analysis_complete:
            time.sleep(0.01)
            self.game.engines[self.cn.next_player].check_alive(exception_if_dead=True)

    def request_analysis(self, extra_settings: dict, *, include_policy: bool) -> dict | None:
        error = None
        analysis = None

        def set_analysis(a, partial_result):
            nonlocal analysis
            if not partial_result:
                analysis = a

        def set_error(a):
            nonlocal error
            error = a

        engine = self.game.engines[self.cn.player]
        engine.request_analysis(
            self.cn,
            callback=set_analysis,
            error_callback=set_error,
            priority=PRIORITY_EXTRA_AI_QUERY,
            ownership=False,
            include_policy=include_policy,
            extra_settings=extra_settings,
        )

        while analysis is None and error is None:
            time.sleep(0.01)
            engine.check_alive(exception_if_dead=True)

        if error is not None:
            self.game.katrain.log(f"[{self.strategy_name}] Error in additional analysis query: {error}", OUTPUT_ERROR)
            return None
        return analysis


@register_strategy(AI_DEFAULT)
class DefaultStrategy(AIStrategy):
    """Full-strength KataGo: play the top engine move."""

    def generate_move(self) -> tuple[Move, str]:
        self.wait_for_analysis()
        candidate_moves = self.cn.candidate_moves
        if not candidate_moves:
            move = Move(is_pass=True, player=self.cn.next_player)
        else:
            move = Move.from_gtp(candidate_moves[0]["move"], player=self.cn.next_player)
        return move, f"Default: played {move.gtp()}."


@register_strategy(AI_HUMAN)
class HumanStyleStrategy(AIStrategy):
    """HumanSL strategy: sample moves from the human policy distribution.

    Supports two profile styles under a single strategy:
    - rank-based (kyu/dan + modern/pre-AZ)
    - pro-year profiles
    """

    def generate_move(self) -> tuple[Move, str]:
        self.game.katrain.log("[HumanStyleStrategy] Generating HumanSL move", OUTPUT_DEBUG)

        profile = human_profile_string(self.settings)
        analysis = self.request_analysis(
            {
                "humanSLProfile": profile,
                "ignorePreRootHistory": False,
            },
            include_policy=True,
        )
        if not analysis:
            self.game.katrain.log("[HumanStyleStrategy] Falling back to default (analysis failed).", OUTPUT_ERROR)
            return DefaultStrategy(self.game, {}).generate_move()

        human_policy = analysis.get("humanPolicy")
        if not human_policy:
            self.game.katrain.log(
                "[HumanStyleStrategy] humanPolicy missing (human model not configured?). Falling back to default.",
                OUTPUT_ERROR,
            )
            return DefaultStrategy(self.game, {}).generate_move()

        board_x, board_y = self.game.board_size
        moves: list[tuple[Move, float]] = []
        for x in range(board_x):
            for y in range(board_y):
                idx = (board_y - y - 1) * board_x + x
                if idx < len(human_policy) and human_policy[idx] > 0:
                    moves.append((Move((x, y), player=self.cn.next_player), human_policy[idx]))

        # Pass move lives at the end if present.
        pass_idx = board_x * board_y
        if pass_idx < len(human_policy) and human_policy[pass_idx] > 0:
            moves.append((Move(None, player=self.cn.next_player), human_policy[pass_idx]))

        if not moves:
            self.game.katrain.log("[HumanStyleStrategy] No moves from human policy. Falling back to default.", OUTPUT_ERROR)
            return DefaultStrategy(self.game, {}).generate_move()

        # Optional SHAPE-like sampling controls to bound randomness:
        # - human_top_k: consider only first K policy moves
        # - human_top_p: keep smallest set with cumulative probability >= P
        # - human_min_p: keep moves with prob >= min_p * best_prob
        top_k = int(self.settings.get("human_top_k", 10_000))
        top_p = float(self.settings.get("human_top_p", 1e9))
        min_p = float(self.settings.get("human_min_p", 0.0))

        ranked_moves = sorted(moves, key=lambda mv: mv[1], reverse=True)
        filtered: list[tuple[Move, float]] = []
        total_prob = 0.0
        best_prob = ranked_moves[0][1]
        stop_reason = "all"
        for i, (move, prob) in enumerate(ranked_moves, start=1):
            if prob < min_p * best_prob:
                stop_reason = "min_p"
                break
            filtered.append((move, prob))
            total_prob += prob
            if i >= top_k:
                stop_reason = "top_k"
                break
            if total_prob >= top_p:
                stop_reason = "top_p"
                break

        sampling_pool = filtered or ranked_moves
        move, prob = weighted_selection_without_replacement(sampling_pool, 1)[0]
        return move, f"HumanSL({profile},{stop_reason}): played {move.gtp()} ({prob:.1%})."


def generate_ai_move(game: Game, ai_mode: str, ai_settings: dict) -> tuple[Move, GameNode]:
    """Generate a move using the selected AI strategy."""

    game.katrain.log(f"Generate AI move called with mode: {ai_mode}", OUTPUT_DEBUG)

    try:
        strategy_cls = STRATEGY_REGISTRY[ai_mode]
    except KeyError:
        game.katrain.log(f"Unknown AI mode {ai_mode!r}, falling back to {AI_DEFAULT}.", OUTPUT_ERROR)
        strategy_cls = STRATEGY_REGISTRY[AI_DEFAULT]

    strategy = strategy_cls(game, ai_settings)
    move, ai_thoughts = strategy.generate_move()

    played_node = game.play(move)
    played_node.ai_thoughts = ai_thoughts
    return move, played_node
