import heapq
import math
import random
import time
from typing import Dict, List, Optional, Tuple

from katrain.core.constants import (
    AI_DEFAULT,
    AI_HANDICAP,
    AI_INFLUENCE,
    AI_INFLUENCE_ELO_GRID,
    AI_JIGO,
    AI_LOCAL,
    AI_LOCAL_ELO_GRID,
    AI_PICK,
    AI_PICK_ELO_GRID,
    AI_POLICY,
    AI_RANK,
    AI_SCORELOSS,
    AI_SCORELOSS_ELO,
    AI_SETTLE_STONES,
    AI_SIMPLE_OWNERSHIP,
    AI_STRATEGIES_PICK,
    AI_STRATEGIES_POLICY,
    AI_STRENGTH,
    AI_TENUKI,
    AI_TENUKI_ELO_GRID,
    AI_TERRITORY,
    AI_TERRITORY_ELO_GRID,
    AI_WEIGHTED,
    AI_WEIGHTED_ELO,
    CALIBRATED_RANK_ELO,
    OUTPUT_DEBUG,
    OUTPUT_ERROR,
    OUTPUT_INFO,
)
from katrain.core.game import Game, GameNode, Move
from katrain.core.utils import var_to_grid


def interp_ix(lst, x):
    i = 0
    while i + 1 < len(lst) - 1 and lst[i + 1] < x:
        i += 1
    t = max(0, min(1, (x - lst[i]) / (lst[i + 1] - lst[i])))
    return i, t


def interp1d(lst, x):
    xs, ys = zip(*lst)
    i, t = interp_ix(xs, x)
    return (1 - t) * ys[i] + t * ys[i + 1]


def interp2d(gridspec, x, y):
    xs, ys, matrix = gridspec
    i, t = interp_ix(xs, x)
    j, s = interp_ix(ys, y)
    return (
        matrix[j][i] * (1 - t) * (1 - s)
        + matrix[j][i + 1] * t * (1 - s)
        + matrix[j + 1][i] * (1 - t) * s
        + matrix[j + 1][i + 1] * t * s
    )


def ai_rank_estimation(strategy, settings) -> int:
    if strategy in [AI_DEFAULT, AI_HANDICAP, AI_JIGO]:
        return 9
    if strategy == AI_RANK:
        return 1 - settings["kyu_rank"]
    if strategy in [AI_WEIGHTED, AI_SCORELOSS, AI_LOCAL, AI_TENUKI, AI_TERRITORY, AI_INFLUENCE, AI_PICK]:
        if strategy == AI_WEIGHTED:
            elo = interp1d(AI_WEIGHTED_ELO, settings["weaken_fac"])
        if strategy == AI_SCORELOSS:
            elo = interp1d(AI_SCORELOSS_ELO, settings["strength"])
        if strategy == AI_PICK:
            elo = interp2d(AI_PICK_ELO_GRID, settings["pick_frac"], settings["pick_n"])
        if strategy == AI_LOCAL:
            elo = interp2d(AI_LOCAL_ELO_GRID, settings["pick_frac"], settings["pick_n"])
        if strategy == AI_TENUKI:
            elo = interp2d(AI_TENUKI_ELO_GRID, settings["pick_frac"], settings["pick_n"])
        if strategy == AI_TERRITORY:
            elo = interp2d(AI_TERRITORY_ELO_GRID, settings["pick_frac"], settings["pick_n"])
        if strategy == AI_INFLUENCE:
            elo = interp2d(AI_INFLUENCE_ELO_GRID, settings["pick_frac"], settings["pick_n"])

        kyu = interp1d(CALIBRATED_RANK_ELO, elo)
        return 1 - kyu
    else:
        return AI_STRENGTH[strategy]


def weighted_selection_without_replacement(items: List[Tuple], pick_n: int) -> List[Tuple]:
    """For a list of tuples where the second element is a weight, returns random items with those weights, without replacement."""
    elt = [(math.log(random.random()) / (item[1] + 1e-18), item) for item in items]  # magic
    return [e[1] for e in heapq.nlargest(pick_n, elt)]  # NB fine if too small


def dirichlet_noise(num, dir_alpha=0.3):
    sample = [random.gammavariate(dir_alpha, 1) for _ in range(num)]
    sum_sample = sum(sample)
    return [s / sum_sample for s in sample]


def fmt_moves(moves: List[Tuple[float, Move]]):
    return ", ".join(f"{mv.gtp()} ({p:.2%})" for p, mv in moves)


def policy_weighted_move(policy_moves, lower_bound, weaken_fac):
    lower_bound, weaken_fac = max(0, lower_bound), max(0.01, weaken_fac)
    weighted_coords = [
        (pv, pv ** (1 / weaken_fac), move) for pv, move in policy_moves if pv > lower_bound and not move.is_pass
    ]
    if weighted_coords:
        top = weighted_selection_without_replacement(weighted_coords, 1)[0]
        move = top[2]
        ai_thoughts = f"Playing policy-weighted random move {move.gtp()} ({top[0]:.1%}) from {len(weighted_coords)} moves above lower_bound of {lower_bound:.1%}."
    else:
        move = policy_moves[0][1]
        ai_thoughts = f"Playing top policy move because no non-pass move > above lower_bound of {lower_bound:.1%}."
    return move, ai_thoughts


def generate_influence_territory_weights(ai_mode, ai_settings, policy_grid, size):
    thr_line = ai_settings["threshold"] - 1  # zero-based
    if ai_mode == AI_INFLUENCE:
        weight = lambda x, y: (1 / ai_settings["line_weight"]) ** (  # noqa E731
            max(0, thr_line - min(size[0] - 1 - x, x)) + max(0, thr_line - min(size[1] - 1 - y, y))
        )  # noqa E731
    else:
        weight = lambda x, y: (1 / ai_settings["line_weight"]) ** (  # noqa E731
            max(0, min(size[0] - 1 - x, x, size[1] - 1 - y, y) - thr_line)
        )
    weighted_coords = [
        (policy_grid[y][x] * weight(x, y), weight(x, y), x, y)
        for x in range(size[0])
        for y in range(size[1])
        if policy_grid[y][x] > 0
    ]
    ai_thoughts = f"Generated weights for {ai_mode} according to weight factor {ai_settings['line_weight']} and distance from {thr_line + 1}th line. "
    return weighted_coords, ai_thoughts


def generate_local_tenuki_weights(ai_mode, ai_settings, policy_grid, cn, size):
    var = ai_settings["stddev"] ** 2
    mx, my = cn.move.coords
    weighted_coords = [
        (policy_grid[y][x], math.exp(-0.5 * ((x - mx) ** 2 + (y - my) ** 2) / var), x, y)
        for x in range(size[0])
        for y in range(size[1])
        if policy_grid[y][x] > 0
    ]
    ai_thoughts = f"Generated weights based on one minus gaussian with variance {var} around coordinates {mx},{my}. "
    if ai_mode == AI_TENUKI:
        weighted_coords = [(p, 1 - w, x, y) for p, w, x, y in weighted_coords]
        ai_thoughts = (
            f"Generated weights based on one minus gaussian with variance {var} around coordinates {mx},{my}. "
        )
    return weighted_coords, ai_thoughts


def request_ai_analysis(game: Game, cn: GameNode, extra_settings: Dict) -> Optional[Dict]:
    error = False
    analysis = None

    def set_analysis(a, partial_result):
        nonlocal analysis
        if not partial_result:
            analysis = a

    def set_error(a):
        nonlocal error
        game.katrain.log(f"Error in additional analysis query: {a}")
        error = True

    engine = game.engines[cn.player]
    engine.request_analysis(
        cn,
        callback=set_analysis,
        error_callback=set_error,
        priority=1_000,
        ownership=False,
        extra_settings=extra_settings,
    )
    while not (error or analysis):
        time.sleep(0.01)
        engine.check_alive(exception_if_dead=True)
    return analysis


def generate_ai_move(game: Game, ai_mode: str, ai_settings: Dict) -> Tuple[Move, GameNode]:
    cn = game.current_node

    if ai_mode == AI_HANDICAP:
        pda = ai_settings["pda"]
        if ai_settings["automatic"]:
            n_handicaps = len(game.root.get_list_property("AB", []))
            MOVE_VALUE = 14  # could be rules dependent
            b_stones_advantage = max(n_handicaps - 1, 0) - (cn.komi - MOVE_VALUE / 2) / MOVE_VALUE
            pda = min(3, max(-3, -b_stones_advantage * (3 / 8)))  # max PDA at 8 stone adv, normal 9 stone game is 8.46
        handicap_analysis = request_ai_analysis(
            game, cn, {"playoutDoublingAdvantage": pda, "playoutDoublingAdvantagePla": "BLACK"}
        )
        if not handicap_analysis:
            game.katrain.log("Error getting handicap-based move", OUTPUT_ERROR)
            ai_mode = AI_DEFAULT

    while not cn.analysis_complete:
        time.sleep(0.01)
        game.engines[cn.next_player].check_alive(exception_if_dead=True)

    ai_thoughts = ""
    if (ai_mode in AI_STRATEGIES_POLICY) and cn.policy:  # pure policy based move
        policy_moves = cn.policy_ranking
        pass_policy = cn.policy[-1]
        # dont make it jump around for the last few sensible non pass moves
        top_5_pass = any([polmove[1].is_pass for polmove in policy_moves[:5]])

        size = game.board_size
        policy_grid = var_to_grid(cn.policy, size)  # type: List[List[float]]
        top_policy_move = policy_moves[0][1]
        ai_thoughts += f"Using policy based strategy, base top 5 moves are {fmt_moves(policy_moves[:5])}. "
        if (ai_mode == AI_POLICY and cn.depth <= ai_settings["opening_moves"]) or (
            ai_mode in [AI_LOCAL, AI_TENUKI] and not (cn.move and cn.move.coords)
        ):
            ai_mode = AI_WEIGHTED
            ai_thoughts += "Strategy override, using policy-weighted strategy instead. "
            ai_settings = {"pick_override": 0.9, "weaken_fac": 1, "lower_bound": 0.02}

        if top_5_pass:
            aimove = top_policy_move
            ai_thoughts += "Playing top one because one of them is pass."
        elif ai_mode == AI_POLICY:
            aimove = top_policy_move
            ai_thoughts += f"Playing top policy move {aimove.gtp()}."
        else:  # weighted or pick-based
            legal_policy_moves = [(pol, mv) for pol, mv in policy_moves if not mv.is_pass and pol > 0]
            board_squares = size[0] * size[1]
            if ai_mode == AI_RANK:  # calibrated, override from 0.8 at start to ~0.4 at full board
                override = 0.8 * (1 - 0.5 * (board_squares - len(legal_policy_moves)) / board_squares)
                overridetwo = 0.85 + max(0, 0.02 * (ai_settings["kyu_rank"] - 8))
            else:
                override = ai_settings["pick_override"]
                overridetwo = 1.0

            if policy_moves[0][0] > override:
                aimove = top_policy_move
                ai_thoughts += f"Top policy move has weight > {override:.1%}, so overriding other strategies."
            elif policy_moves[0][0] + policy_moves[1][0] > overridetwo:
                aimove = top_policy_move
                ai_thoughts += (
                    f"Top two policy moves have cumulative weight > {overridetwo:.1%}, so overriding other strategies."
                )
            elif ai_mode == AI_WEIGHTED:
                aimove, ai_thoughts = policy_weighted_move(
                    policy_moves, ai_settings["lower_bound"], ai_settings["weaken_fac"]
                )
            elif ai_mode in AI_STRATEGIES_PICK:

                if ai_mode != AI_RANK:
                    n_moves = max(1, int(ai_settings["pick_frac"] * len(legal_policy_moves) + ai_settings["pick_n"]))
                else:
                    orig_calib_avemodrank = 0.063015 + 0.7624 * board_squares / (
                        10 ** (-0.05737 * ai_settings["kyu_rank"] + 1.9482)
                    )
                    norm_leg_moves = len(legal_policy_moves) / board_squares
                    modified_calib_avemodrank = (
                        0.3931
                        + 0.6559
                        * norm_leg_moves
                        * math.exp(
                            -1
                            * (
                                3.002 * norm_leg_moves * norm_leg_moves
                                - norm_leg_moves
                                - 0.034889 * ai_settings["kyu_rank"]
                                - 0.5097
                            )
                            ** 2
                        )
                        - 0.01093 * ai_settings["kyu_rank"]
                    ) * orig_calib_avemodrank
                    n_moves = board_squares * norm_leg_moves / (1.31165 * (modified_calib_avemodrank + 1) - 0.082653)
                    n_moves = max(1, round(n_moves))

                if ai_mode in [AI_INFLUENCE, AI_TERRITORY, AI_LOCAL, AI_TENUKI]:
                    if cn.depth > ai_settings["endgame"] * board_squares:
                        weighted_coords = [(pol, 1, *mv.coords) for pol, mv in legal_policy_moves]
                        x_ai_thoughts = (
                            f"Generated equal weights as move number >= {ai_settings['endgame'] * size[0] * size[1]}. "
                        )
                        n_moves = int(max(n_moves, len(legal_policy_moves) // 2))
                    elif ai_mode in [AI_INFLUENCE, AI_TERRITORY]:
                        weighted_coords, x_ai_thoughts = generate_influence_territory_weights(
                            ai_mode, ai_settings, policy_grid, size
                        )
                    else:  # ai_mode in [AI_LOCAL, AI_TENUKI]
                        weighted_coords, x_ai_thoughts = generate_local_tenuki_weights(
                            ai_mode, ai_settings, policy_grid, cn, size
                        )
                    ai_thoughts += x_ai_thoughts
                else:  # ai_mode in [AI_PICK, AI_RANK]:
                    weighted_coords = [
                        (policy_grid[y][x], 1, x, y)
                        for x in range(size[0])
                        for y in range(size[1])
                        if policy_grid[y][x] > 0
                    ]

                pick_moves = weighted_selection_without_replacement(weighted_coords, n_moves)
                ai_thoughts += f"Picked {min(n_moves,len(weighted_coords))} random moves according to weights. "

                if pick_moves:
                    new_top = [
                        (p, Move((x, y), player=cn.next_player)) for p, wt, x, y in heapq.nlargest(5, pick_moves)
                    ]
                    aimove = new_top[0][1]
                    ai_thoughts += f"Top 5 among these were {fmt_moves(new_top)} and picked top {aimove.gtp()}. "
                    if new_top[0][0] < pass_policy:
                        ai_thoughts += f"But found pass ({pass_policy:.2%} to be higher rated than {aimove.gtp()} ({new_top[0][0]:.2%}) so will play top policy move instead."
                        aimove = top_policy_move
                else:
                    aimove = top_policy_move
                    ai_thoughts += f"Pick policy strategy {ai_mode} failed to find legal moves, so is playing top policy move {aimove.gtp()}."
            else:
                raise ValueError(f"Unknown Policy-based AI mode {ai_mode}")
    else:  # Engine based move
        candidate_ai_moves = cn.candidate_moves
        if ai_mode == AI_HANDICAP:
            candidate_ai_moves = handicap_analysis["moveInfos"]

        top_cand = Move.from_gtp(candidate_ai_moves[0]["move"], player=cn.next_player)
        if top_cand.is_pass and ai_mode not in [
            AI_DEFAULT,
            AI_HANDICAP,
        ]:  # don't play suicidal to balance score
            aimove = top_cand
            ai_thoughts += "Top move is pass, so passing regardless of strategy. "
        else:
            if ai_mode == AI_JIGO:
                sign = cn.player_sign(cn.next_player)
                jigo_move = min(
                    candidate_ai_moves, key=lambda move: abs(sign * move["scoreLead"] - ai_settings["target_score"])
                )
                aimove = Move.from_gtp(jigo_move["move"], player=cn.next_player)
                ai_thoughts += f"Jigo strategy found {len(candidate_ai_moves)} candidate moves (best {top_cand.gtp()}) and chose {aimove.gtp()} as closest to 0.5 point win"
            elif ai_mode == AI_SCORELOSS:
                c = ai_settings["strength"]
                moves = [
                    (
                        d["pointsLost"],
                        math.exp(min(200, -c * max(0, d["pointsLost"]))),
                        Move.from_gtp(d["move"], player=cn.next_player),
                    )
                    for d in candidate_ai_moves
                ]
                topmove = weighted_selection_without_replacement(moves, 1)[0]
                aimove = topmove[2]
                ai_thoughts += f"ScoreLoss strategy found {len(candidate_ai_moves)} candidate moves (best {top_cand.gtp()}) and chose {aimove.gtp()} (weight {topmove[1]:.3f}, point loss {topmove[0]:.1f}) based on score weights."
            elif ai_mode in [AI_SIMPLE_OWNERSHIP, AI_SETTLE_STONES]:
                stones_with_player = {(*s.coords, s.player) for s in game.stones}
                next_player_sign = cn.player_sign(cn.next_player)
                if ai_mode == AI_SIMPLE_OWNERSHIP:

                    def settledness(d, player_sign, player):
                        return sum([abs(o) for o in d["ownership"] if player_sign * o > 0])

                else:
                    board_size_x, board_size_y = game.board_size

                    def settledness(d, player_sign, player):
                        ownership_grid = var_to_grid(d["ownership"], (board_size_x, board_size_y))
                        return sum(
                            [abs(ownership_grid[s.coords[0]][s.coords[1]]) for s in game.stones if s.player == player]
                        )

                def is_attachment(move):
                    if move.is_pass:
                        return False
                    attach_opponent_stones = sum(
                        (move.coords[0] + dx, move.coords[1] + dy, cn.player) in stones_with_player
                        for dx in [-1, 0, 1]
                        for dy in [-1, 0, 1]
                        if abs(dx) + abs(dy) == 1
                    )
                    nearby_own_stones = sum(
                        (move.coords[0] + dx, move.coords[1] + dy, cn.next_player) in stones_with_player
                        for dx in [-2, 0, 1, 2]
                        for dy in [-2 - 1, 0, 1, 2]
                        if abs(dx) + abs(dy) <= 2  # allows clamps/jumps
                    )
                    return attach_opponent_stones >= 1 and nearby_own_stones == 0

                def is_tenuki(d):
                    return not d.is_pass and not any(
                        not node
                        or not node.move
                        or node.move.is_pass
                        or max(abs(last_c - cand_c) for last_c, cand_c in zip(node.move.coords, d.coords)) < 5
                        for node in [cn, cn.parent]
                    )

                moves_with_settledness = sorted(
                    [
                        (
                            move,
                            settledness(d, next_player_sign, cn.next_player),
                            settledness(d, -next_player_sign, cn.player),
                            is_attachment(move),
                            is_tenuki(move),
                            d,
                        )
                        for d in candidate_ai_moves
                        if d["pointsLost"] < ai_settings["max_points_lost"]
                        and "ownership" in d
                        and (d["order"] <= 1 or d["visits"] >= ai_settings.get("min_visits", 1))
                        for move in [Move.from_gtp(d["move"], player=cn.next_player)]
                        if not (move.is_pass and d["pointsLost"] > 0.75)
                    ],
                    key=lambda t: t[5]["pointsLost"]
                    + ai_settings["attach_penalty"] * t[3]
                    + ai_settings["tenuki_penalty"] * t[4]
                    - ai_settings["settled_weight"] * (t[1] + ai_settings["opponent_fac"] * t[2]),
                )
                if moves_with_settledness:
                    cands = [
                        f"{move.gtp()} ({d['pointsLost']:.1f} pt lost, {d['visits']} visits, {settled:.1f} settledness, {oppsettled:.1f} opponent settledness{', attachment' if isattach else ''}{', tenuki' if istenuki else ''})"
                        for move, settled, oppsettled, isattach, istenuki, d in moves_with_settledness[:5]
                    ]
                    ai_thoughts += f"{ai_mode} strategy. Top 5 Candidates {', '.join(cands)} "
                    aimove = moves_with_settledness[0][0]
                else:
                    raise (Exception("No moves found - are you using an older KataGo with no per-move ownership info?"))
            else:
                if ai_mode not in [AI_DEFAULT, AI_HANDICAP]:
                    game.katrain.log(f"Unknown AI mode {ai_mode} or policy missing, using default.", OUTPUT_INFO)
                    ai_thoughts += f"Strategy {ai_mode} not found or unexpected fallback."
                aimove = top_cand
                if ai_mode == AI_HANDICAP:
                    ai_thoughts += f"Handicap strategy found {len(candidate_ai_moves)} moves returned from the engine and chose {aimove.gtp()} as top move. PDA based score {cn.format_score(handicap_analysis['rootInfo']['scoreLead'])} and win rate {cn.format_winrate(handicap_analysis['rootInfo']['winrate'])}"
                else:
                    ai_thoughts += f"Default strategy found {len(candidate_ai_moves)} moves returned from the engine and chose {aimove.gtp()} as top move"
    game.katrain.log(f"AI thoughts: {ai_thoughts}", OUTPUT_DEBUG)
    played_node = game.play(aimove)
    played_node.ai_thoughts = ai_thoughts
    return aimove, played_node
