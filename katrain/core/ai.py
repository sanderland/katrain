import heapq
import math
import random
import time
from typing import Dict, List, Tuple

from katrain.core.common import OUTPUT_DEBUG, OUTPUT_INFO, var_to_grid
from katrain.core.engine import EngineDiedException
from katrain.core.game import Game, GameNode, Move


def weighted_selection_without_replacement(items: List[Tuple], pick_n: int) -> List[Tuple]:
    """For a list of tuples where the second element is a weight, returns random items with those weights, without replacement."""
    elt = [(math.log(random.random()) / item[1], item) for item in items]  # magic
    return [e[1] for e in heapq.nlargest(pick_n, elt)]  # NB fine if too small


def dirichlet_noise(num, dir_alpha=0.3):
    sample = [random.gammavariate(dir_alpha, 1) for _ in range(num)]
    sum_sample = sum(sample)
    return [s / sum_sample for s in sample]


def fmt_moves(moves: List[Tuple[float, Move]]):
    return ", ".join(f"{mv.gtp()} ({p:.2%})" for p, mv in moves)


def ai_move(game: Game, ai_mode: str, ai_settings: Dict) -> Tuple[Move, GameNode]:
    cn = game.current_node
    while not cn.analysis_ready:
        time.sleep(0.01)
        engine = game.engines[cn.next_player]
        if engine.katago_process.poll() is not None:  # TODO: clean up
            raise EngineDiedException(f"Engine for {cn.next_player} ({engine.config}) died")
    ai_mode = ai_mode.lower()
    ai_thoughts = ""
    if ("policy" in ai_mode or "p:" in ai_mode) and cn.policy:  # pure policy based move
        policy_moves = cn.policy_ranking
        pass_policy = cn.policy[-1]
        top_5_pass = any([polmove[1].is_pass for polmove in policy_moves[:5]])  # dont make it jump around for the last few sensible non pass moves

        size = game.board_size
        policy_grid = var_to_grid(cn.policy, size)  # type: List[List[float]]
        top_policy_move = policy_moves[0][1]
        ai_thoughts += f"Using policy based strategy, base top 5 moves are {fmt_moves(policy_moves[:5])}. "
        if "policy" in ai_mode and cn.depth <= int(ai_settings["opening_moves"] * (game.board_size[0] * game.board_size[1])):
            ai_mode = "p:weighted"
            ai_thoughts += f"Switching to weighted strategy in the opening {int(ai_settings['opening_moves'] * (game.board_size[0]*game.board_size[1]))} moves. "
            ai_settings = {"pick_override": 0.9, "weaken_fac": 1, "lower_bound": 0.02}
        if top_5_pass:
            aimove = top_policy_move
            ai_thoughts += "Playing top one because one of them is pass."
        elif "policy" in ai_mode:
            aimove = top_policy_move
            ai_thoughts += f"Playing top policy move {aimove.gtp()}."
        elif policy_moves[0][0] > ai_settings["pick_override"]:
            aimove = top_policy_move
            ai_thoughts += f"Top policy move has weight > {ai_settings['pick_override']:.1%}, so overriding other strategies."
        elif "weighted" in ai_mode:
            lower_bound = max(0, ai_settings["lower_bound"]) * 2  # compensate for first halving in loop
            weaken_fac = max(0.01, ai_settings["weaken_fac"])
            weighted_coords = []
            while not weighted_coords and lower_bound > 1e-6:  # fix edge case where no moves are > lb
                lower_bound /= 2
                weighted_coords = [
                    (policy_grid[y][x], policy_grid[y][x] ** (1 / weaken_fac), x, y) for x in range(size[0]) for y in range(size[1]) if policy_grid[y][x] > lower_bound
                ]
            top = weighted_selection_without_replacement(weighted_coords, 1)
            if top:
                best = top[0]
                policy_value = best[0]
                coords = best[2:]
            else:
                policy_value = pass_policy
                coords = None
            aimove = Move(coords, player=cn.next_player)  # just take a random move by policy w/o noise
            ai_thoughts += f"Playing policy-weighted random move {aimove.gtp()} ({policy_value:.1%})" + (
                " because no other moves were found." if not top else f" because strategy is weighted (lower bound={lower_bound:.2%}, num moves > lb={len(weighted_coords)})."
            )
        elif "noise" in ai_mode:  # DEPRECATED
            noise_str = ai_settings["noise_strength"]
            lower_bound = max(0, ai_settings["lower_bound"])
            selected_policy_moves = [(pol, mv) for pol, mv in policy_moves if not mv.is_pass if pol > lower_bound]
            d_noise = dirichlet_noise(len(selected_policy_moves))
            noisy_policy_moves = [(((1 - noise_str) * pol + noise_str * noise), mv) for ((pol, mv), noise) in zip(selected_policy_moves, d_noise)]
            new_top = heapq.nlargest(5, noisy_policy_moves)
            ai_thoughts += f"Noisy policy strategy (strength={noise_str:.2f}) generated 5 moves {fmt_moves(new_top)} "
            aimove = new_top[0][1]
            if new_top[0][0] < pass_policy:
                ai_thoughts += f", but found pass ({pass_policy:.2%} to be higher rated than {aimove.gtp()} ({new_top[0][0]:.2%}) so will play top policy move instead."
                aimove = top_policy_move
            else:
                ai_thoughts += f" so picked {aimove.gtp()} ({policy_grid[aimove.coords[1]][aimove.coords[0]]:.2%})."
        elif "p:" in ai_mode:
            legal_policy_moves = [(pol, mv) for pol, mv in policy_moves if not mv.is_pass if pol > 0]
            n_moves = int(ai_settings["pick_frac"] * len(legal_policy_moves) + ai_settings["pick_n"])
            if "influence" in ai_mode or "territory" in ai_mode:

                thr_line = ai_settings["threshold"] - 1  # zero-based
                if cn.depth >= ai_settings["endgame"] * size[0] * size[1]:
                    weighted_coords = [(policy_grid[y][x], 1, x, y) for x in range(size[0]) for y in range(size[1]) if policy_grid[y][x] > 0]
                    ai_thoughts += f"Generated equal weights as move number >= {ai_settings['endgame'] * size[0] * size[1]}. "
                else:
                    if "influence" in ai_mode:
                        weight = lambda x, y: (1 / ai_settings["line_weight"]) ** (max(0, thr_line - min(size[0] - 1 - x, x)) + max(0, thr_line - min(size[1] - 1 - y, y)))
                    else:
                        weight = lambda x, y: (1 / ai_settings["line_weight"]) ** (max(0, min(size[0] - 1 - x, x, size[1] - 1 - y, y) - thr_line))
                    weighted_coords = [(policy_grid[y][x] * weight(x, y), weight(x, y), x, y) for x in range(size[0]) for y in range(size[1]) if policy_grid[y][x] > 0]
                    ai_thoughts += f"Generated weights for {ai_mode} according to weight factor {ai_settings['line_weight']} and distance from {thr_line+1}th line. "
            elif "local" in ai_mode or "tenuki" in ai_mode:
                var = ai_settings["stddev"] ** 2
                if not cn.move or cn.move.coords is None:
                    weighted_coords = [(1, 1, *top_policy_move.coords)]  # if "pick" in ai_mode -> even
                    ai_thoughts += f"No previous non-pass move, faking weights to play top policy move. "
                else:
                    mx, my = cn.move.coords
                    weighted_coords = [
                        (policy_grid[y][x], math.exp(-0.5 * ((x - mx) ** 2 + (y - my) ** 2) / var), x, y) for x in range(size[0]) for y in range(size[1]) if policy_grid[y][x] > 0
                    ]
                    if "tenuki" in ai_mode:
                        if cn.depth < ai_settings["endgame"] * size[0] * size[1]:
                            weighted_coords = [(p, 1 - w, x, y) for p, w, x, y in weighted_coords]
                            ai_thoughts += f"Generated weights based on one minus gaussian with variance {var} around coordinates {mx},{my}. "
                        else:
                            weighted_coords = [(p, 1, x, y) for p, w, x, y in weighted_coords]
                            ai_thoughts += f"Generated equal weights as move number >= {ai_settings['endgame'] * size[0] * size[1]}. "
                    else:
                        ai_thoughts += f"Generated weights based on gaussian with variance {var} around coordinates {mx},{my}. "
            elif "pick" in ai_mode:
                weighted_coords = [(policy_grid[y][x], 1, x, y) for x in range(size[0]) for y in range(size[1]) if policy_grid[y][x] > 0]
            else:
                raise ValueError(f"Unknown AI mode {ai_mode}")
            pick_moves = weighted_selection_without_replacement(weighted_coords, n_moves)
            ai_thoughts += f"Picked {min(n_moves,len(weighted_coords))} random moves according to weights. "
            if pick_moves:
                new_top = [(p, Move((x, y), player=cn.next_player)) for p, wt, x, y in heapq.nlargest(5, pick_moves)]
                aimove = new_top[0][1]
                ai_thoughts += f"Top 5 among these were {fmt_moves(new_top)} and picked top {aimove.gtp()}. "
                if new_top[0][0] < pass_policy:
                    ai_thoughts += f"But found pass ({pass_policy:.2%} to be higher rated than {aimove.gtp()} ({new_top[0][0]:.2%}) so will play top policy move instead."
                    aimove = top_policy_move
            else:
                aimove = top_policy_move
                ai_thoughts += f"Pick policy strategy {ai_mode} failed to find legal moves, so is playing top policy move {aimove.gtp()}."
        else:
            raise ValueError(f"Unknown AI mode {ai_mode}")
    else:  # Engine based move
        candidate_ai_moves = cn.candidate_moves
        top_cand = Move.from_gtp(candidate_ai_moves[0]["move"], player=cn.next_player)
        if top_cand.is_pass:  # don't play suicidal to balance score - pass when it's best
            aimove = top_cand
            ai_thoughts += f"Top move is pass, so passing regardless of strategy."
        else:
            if "balance" in ai_mode:
                sign = cn.player_sign(cn.next_player)
                sel_moves = [  # top move, or anything not too bad, or anything that makes you still ahead
                    move
                    for i, move in enumerate(candidate_ai_moves)
                    if i == 0
                    or move["visits"] >= ai_settings["min_visits"]
                    and (move["pointsLost"] < ai_settings["random_loss"] or move["pointsLost"] < ai_settings["max_loss"] and sign * move["scoreLead"] > ai_settings["target_score"])
                ]
                aimove = Move.from_gtp(random.choice(sel_moves)["move"], player=cn.next_player)
                ai_thoughts += f"Balance strategy selected moves {sel_moves} based on target score and max points lost, and randomly chose {aimove.gtp()}."
            elif "jigo" in ai_mode:
                sign = cn.player_sign(cn.next_player)
                jigo_move = min(candidate_ai_moves, key=lambda move: abs(sign * move["scoreLead"] - ai_settings["target_score"]))
                aimove = Move.from_gtp(jigo_move["move"], player=cn.next_player)
                ai_thoughts += f"Jigo strategy found {len(candidate_ai_moves)} candidate moves (best {top_cand.gtp()}) and chose {aimove.gtp()} as closest to 0.5 point win"
            elif "scoreloss" in ai_mode:
                c = ai_settings["strength"]
                moves = [(d["pointsLost"], math.exp(min(200, -c * max(0, d["pointsLost"]))), Move.from_gtp(d["move"], player=cn.next_player)) for d in candidate_ai_moves]
                topmove = weighted_selection_without_replacement(moves, 1)[0]
                aimove = topmove[2]
                ai_thoughts += f"ScoreLoss strategy found {len(candidate_ai_moves)} candidate moves (best {top_cand.gtp()}) and chose {aimove.gtp()} (weight {topmove[1]:.3f}, point loss {topmove[0]:.1f}) based on score weights."
            else:
                if "default" not in ai_mode and "katago" not in ai_mode:
                    game.katrain.log(f"Unknown AI mode {ai_mode} or policy missing, using default.", OUTPUT_INFO)
                    ai_thoughts += f"Strategy {ai_mode} not found or unexpected fallback."
                aimove = top_cand
                ai_thoughts += f"Default strategy found {len(candidate_ai_moves)} moves returned from the engine and chose {aimove.gtp()} as top move"
    game.katrain.log(f"AI thoughts: {ai_thoughts}", OUTPUT_DEBUG)
    played_node = game.play(aimove)
    played_node.ai_thoughts = ai_thoughts
    return aimove, played_node
