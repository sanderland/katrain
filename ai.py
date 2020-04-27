import heapq
import math
import random
import time
from typing import Dict, List, Tuple, Any

import numpy as np

from common import OUTPUT_INFO, var_to_grid, OUTPUT_DEBUG, OUTPUT_ERROR
from engine import EngineDiedException
from game import Move, Game, IllegalMoveException, GameNode


def weighted_selection_without_replacement(items: List[Tuple[float, float, int, int]], pick_n: int) -> List[Tuple[float, float, int, int]]:
    """For a list of tuples where the second element is a weight, returns random items with those weights, without replacement."""
    elt = [(math.log(random.random()) / item[1], item) for item in items]  # magic
    return [e[1] for e in heapq.nlargest(pick_n, elt)]  # NB fine if too small


def dirichlet_noise(num, dir_alpha=0.3):
    return np.random.dirichlet([dir_alpha] * num)


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
    candidate_ai_moves = cn.candidate_moves
    if ("policy" in ai_mode or "p:" in ai_mode) and cn.policy:
        policy_moves = cn.policy_ranking
        pass_policy = cn.policy[-1]
        top_5_pass = any([polmove[1].is_pass for polmove in policy_moves[:5]])  # dont make it jump around for the last few sensible non pass moves

        size = game.board_size
        policy_grid = var_to_grid(cn.policy, size)  # type: List[List[float]]
        legal_policy_moves = [(pol, mv) for pol, mv in policy_moves if not mv.is_pass if pol > 0]
        top_policy_move = policy_moves[0][1]
        ai_thoughts += f"Using policy based strategy, base top 5 moves are {fmt_moves(policy_moves[:5])}. "
        if top_policy_move.is_pass:
            aimove = top_policy_move
            ai_thoughts += "Playing top one because it is pass."
        elif "policy" in ai_mode:
            aimove = top_policy_move
            ai_thoughts += f"Playing top policy move {aimove.gtp()} due to mode chosen."
        elif policy_moves[0][0] > ai_settings["pick_override"]:
            aimove = top_policy_move
            ai_thoughts += f"Top policy move has weight > {ai_settings['pick_override']:.1%}, so overriding other strategies."
        elif top_5_pass or "weighted" in ai_mode:
            weighted_coords = [(policy_grid[y][x], policy_grid[y][x], x, y) for x in range(size[0]) for y in range(size[1]) if policy_grid[y][x] > 0]
            best = weighted_selection_without_replacement(weighted_coords, 1)[0]
            aimove = Move(best[2:], player=cn.next_player)  # just take a random move by policy w/o noise
            ai_thoughts += f"Playing policy-weighted random move {aimove.gtp()} ({best[0]:.1%})" + (
                " because one of them is pass." if top_5_pass else " because strategy is weighted."
            )
        elif "noise" in ai_mode:
            noise_str = ai_settings["noise_strength"]
            d_noise = dirichlet_noise(len(legal_policy_moves))
            noisy_policy_moves = [(((1 - noise_str) * pol + noise_str * noise), mv) for ((pol, mv), noise) in zip(legal_policy_moves, d_noise)]
            new_top = heapq.nlargest(5, noisy_policy_moves)
            aimove = new_top[0][1]
            ai_thoughts += f"Noisy policy strategy (strength={noise_str:.2f}) generated 5 moves {fmt_moves(new_top)} so picked {aimove.gtp()}. "
        elif "p:" in ai_mode:
            n_moves = int(ai_settings["pick_frac"] * len(legal_policy_moves) + ai_settings["pick_n"])
            if "influence" in ai_mode or "territory" in ai_mode:
                if "influence" in ai_mode:
                    weight = lambda x, y: (1 / ai_settings["line_weight"]) ** max(0, 3 - min(size[0] - 1 - x, x, y, size[1] - 1 - y))
                else:
                    weight = lambda x, y: (1 / ai_settings["line_weight"]) ** max(0, min(size[0] - 1 - x, x, y, size[1] - 1 - y) - 2)
                weighted_coords = [(policy_grid[y][x] * weight(x, y), weight(x, y), x, y) for x in range(size[0]) for y in range(size[1]) if policy_grid[y][x] > 0]
                ai_thoughts += f"Generated weights for {ai_mode} according to weight factor {ai_settings['line_weight']} and distance from 4th line. "
            elif "local" in ai_mode or "tenuki" in ai_mode:
                var = ai_settings["stddev"] ** 2
                if not cn.single_move or cn.single_move.coords is None:
                    weighted_coords = [(1, 1, *top_policy_move.coords)]  # if "pick" in ai_mode -> even
                    ai_thoughts += f"No previous non-pass move, faking weights to play top policy move. "
                else:
                    mx, my = cn.single_move.coords
                    weighted_coords = [
                        (policy_grid[y][x], math.exp(-0.5 * ((x - mx) ** 2 + (y - my) ** 2) / var), x, y) for x in range(size[0]) for y in range(size[1]) if policy_grid[y][x] > 0
                    ]
                    if "tenuki" in ai_mode:
                        weighted_coords = [(p, 1 - w, x, y) for p, w, x, y in weighted_coords]
                        ai_thoughts += f"Generated weights based on one minus gaussian with variance {var} around coordinates {mx},{my}. "
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
    elif "balance" in ai_mode and candidate_ai_moves[0]["move"] != "pass":  # don't play suicidal to balance score - pass when it's best
        sign = cn.player_sign(cn.next_player)  # TODO check
        sel_moves = [  # top move, or anything not too bad, or anything that makes you still ahead
            move
            for i, move in enumerate(candidate_ai_moves)
            if i == 0
            or move["visits"] >= ai_settings["min_visits"]
            and (move["pointsLost"] < ai_settings["random_loss"] or move["pointsLost"] < ai_settings["max_loss"] and sign * move["scoreLead"] > ai_settings["target_score"])
        ]
        aimove = Move.from_gtp(random.choice(sel_moves)["move"], player=cn.next_player)  # TODO: could be weighted towards worse
        ai_thoughts += f"Balance strategy selected moves {sel_moves} based on target score and max points lost, and randomly chose {aimove.gtp()}."
    elif "jigo" in ai_mode and candidate_ai_moves[0]["move"] != "pass":
        sign = cn.player_sign(cn.next_player)  # TODO check
        jigo_move = min(candidate_ai_moves, key=lambda move: abs(sign * move["scoreLead"] - ai_settings["target_score"]))
        aimove = Move.from_gtp(jigo_move["move"], player=cn.next_player)
        ai_thoughts += f"Jigo strategy found candidate moves {candidate_ai_moves} moves and chose {aimove.gtp()} as closest to 0.5 point win"
    else:
        if "default" not in ai_mode and "katago" not in ai_mode:
            game.katrain.log(f"Unknown AI mode {ai_mode} or policy missing, using default.", OUTPUT_INFO)
            ai_thoughts += f"Strategy {ai_mode} not found or unexpected fallback."
        aimove = Move.from_gtp(candidate_ai_moves[0]["move"], player=cn.next_player)
        ai_thoughts += f"Default strategy found {len(candidate_ai_moves)} moves returned from the engine and chose {aimove.gtp()} as top move"
    game.katrain.log(f"AI thoughts: {ai_thoughts}", OUTPUT_DEBUG)
    try:
        played_node = game.play(aimove)
        played_node.ai_thoughts = ai_thoughts
        return aimove, played_node
    except IllegalMoveException as e:
        game.katrain.log(f"AI Strategy {ai_mode} generated illegal move {aimove.gtp()}:  {e}", OUTPUT_ERROR)
