import heapq
import math
import random
import time
from typing import Dict

import numpy as np

from common import OUTPUT_INFO, var_to_grid, OUTPUT_DEBUG, OUTPUT_ERROR
from engine import EngineDiedException
from game import Move, Game, IllegalMoveException


def weighted_selection_without_replacement(items, m):
    """For a list of arrays where the first element is a weight, returns random items with those weights, without replacement."""
    elt = [(math.log(random.random()) / item[0], item) for item in items]  # magic
    return [e[1] for e in heapq.nlargest(m, elt)]  # NB fine if too small


def dirichlet_noise(num, dir_alpha=0.3):
    return np.random.dirichlet([dir_alpha] * num)


def ai_move(game: Game, ai_mode: str, ai_settings: Dict):
    cn = game.current_node
    while not cn.analysis_ready:
        time.sleep(0.01)
        engine = game.engines[cn.next_player]
        if engine.katago_process.poll() is not None:  # TODO: clean up
            raise EngineDiedException(f"Engine for {cn.next_player} ({engine.config}) died")
    ai_mode = ai_mode.lower()
    candidate_ai_moves = cn.candidate_moves
    if ("policy" in ai_mode or "p+" in ai_mode) and cn.policy:
        policy_moves = cn.policy_ranking
        pass_policy = cn.policy[-1]
        top_5_pass = any([polmove[0].is_pass for polmove in policy_moves[:5]])  # dont make it jump around for the last few sensible non pass moves

        size = game.board_size
        policy_grid = var_to_grid(cn.policy, size)
        legal_policy_moves = [(mv, pol) for mv, pol in policy_moves if not mv.is_pass if pol > 0]
        top_policy_move = policy_moves[0][0]
        game.katrain.log(f"Policy strategy {ai_mode} found {top_policy_move} as top move", OUTPUT_DEBUG)
        if top_policy_move.is_pass:
            aimove = top_policy_move
        elif top_5_pass:
            weighted_coords = [(policy_grid[y][x], x, y, policy_grid[y][x]) for x in range(size[0]) for y in range(size[1]) if policy_grid[y][x] > 0]
            aimove = Move(weighted_selection_without_replacement(weighted_coords, 1)[0][1:3], player=cn.next_player)  # just take a random move by policy w/o noise
            game.katrain.log(f"Policy strategy {ai_mode} found pass in top 5 moves so chose {aimove} as weighted-by-policy move", OUTPUT_DEBUG)
        elif "policy" in ai_mode:
            aimove = top_policy_move
        elif "noise" in ai_mode:
            noise_str = ai_settings["noise_strength"]
            d_noise = dirichlet_noise(len(legal_policy_moves))
            noisy_policy_moves = [(mv, (1 - noise_str) * pol + noise_str * noise) for ((mv, pol), noise) in zip(legal_policy_moves, d_noise)]
            best = max(noisy_policy_moves, key=lambda mp: mp[1])
            aimove = best[0]
            game.katrain.log(f"Noisy policy strategy (strength={noise_str:.2f}) generated move {aimove.gtp()} with value {best[1]}", OUTPUT_DEBUG)
        elif any(keyword in ai_mode for keyword in ["influence", "territory", "local", "tenuki", "pick"]):
            n_moves = int(ai_settings["pick_frac"] * len(legal_policy_moves) + ai_settings["pick_n"])
            if "influence" in ai_mode or "territory" in ai_mode:

                if "influence" in ai_mode:
                    weight = lambda x, y: ai_settings["influence_weight"] ** max(0, 3 - min(size[0] - 1 - x, x, y, size[1] - 1 - y))
                else:
                    weight = lambda x, y: ai_settings["influence_weight"] ** max(0, min(size[0] - 1 - x, x, y, size[1] - 1 - y) - 2)
                weighted_coords = [(weight(x, y), x, y, policy_grid[y][x] * weight(x, y)) for x in range(size[0]) for y in range(size[1]) if policy_grid[y][x] > 0]
            elif "local" in ai_mode or "tenuki" in ai_mode:
                var = ai_settings["local_stddev"] ** 2
                if not cn.single_move or cn.single_move.coords is None:
                    weighted_coords = [(1, *top_policy_move.coords, 1)]  # if "pick" in ai_mode -> even
                    game.katrain.log(f"Local strategy: no previous non-pass move, playing top policy move {top_policy_move}", OUTPUT_DEBUG)
                else:
                    mx, my = cn.single_move.coords
                    weighted_coords = [
                        (math.exp(-0.5 * ((x - mx) ** 2 + (y - my) ** 2) / var), x, y, policy_grid[y][x]) for x in range(size[0]) for y in range(size[1]) if policy_grid[y][x] > 0
                    ]
                    game.katrain.log(f"Generated weights based on gaussian with var {var} around {mx},{my}", OUTPUT_DEBUG)
                    if "tenuki" in ai_mode:
                        weighted_coords = [(1 - w, x, y, p) for w, x, y, p in weighted_coords]
            elif "pick" in ai_mode:
                weighted_coords = [(1, x, y, policy_grid[y][x]) for x in range(size[0]) for y in range(size[1]) if policy_grid[y][x] > 0]
            else:
                raise ValueError(f"Unknown AI mode {ai_mode}")
            pick_moves = weighted_selection_without_replacement(weighted_coords, n_moves)
            if pick_moves:
                best = max(pick_moves, key=lambda m: m[3])
                aimove = Move((best[1], best[2]), player=cn.next_player)
                game.katrain.log(f"Pick policy strategy {ai_mode} (n={n_moves}) generated move {aimove.gtp()} with weight {best[0]} and value {best[3]}", OUTPUT_DEBUG)
                if best[3] < pass_policy:
                    game.katrain.log(f"Pick policy strategy found pass is better than {aimove} so will pass instead", OUTPUT_DEBUG)
                    aimove = Move(None, player=cn.next_player)
            else:
                aimove = top_policy_move
                game.katrain.log(f"Pick policy strategy {ai_mode} failed to find legal moves, so is playing top policy move {aimove}", OUTPUT_DEBUG)
        else:
            raise ValueError(f"Unknown AI mode {ai_mode}")
    elif "balance" in ai_mode and candidate_ai_moves[0]["move"] != "pass":  # don't play suicidal to balance score - pass when it's best
        sign = cn.player_sign(cn.next_player)  # TODO check
        sel_moves = [  # top move, or anything not too bad, or anything that makes you still ahead
            move
            for i, move in enumerate(candidate_ai_moves)
            if i == 0
            or move["visits"] >= ai_settings["balance_min_visits"]
            and (
                move["pointsLost"] < ai_settings["balance_random_loss"]
                or move["pointsLost"] < ai_settings["balance_max_loss"]
                and sign * move["scoreLead"] > ai_settings["balance_target_score"]
            )
        ]
        aimove = Move.from_gtp(random.choice(sel_moves)["move"], player=cn.next_player)  # TODO: could be weighted towards worse
        game.katrain.log(f"Balance strategy considered {len(sel_moves)} moves and chose {aimove} randomly", OUTPUT_DEBUG)
    elif "jigo" in ai_mode and candidate_ai_moves[0]["move"] != "pass":
        sign = cn.player_sign(cn.next_player)  # TODO check
        jigo_move = min(candidate_ai_moves, key=lambda move: abs(sign * move["scoreLead"] - 0.5))
        aimove = Move.from_gtp(jigo_move["move"], player=cn.next_player)
        game.katrain.log(f"Jigo strategy found {len(candidate_ai_moves)} moves and chose {aimove} as closest to 0.5 point win", OUTPUT_DEBUG)
    else:
        if "default" not in ai_mode and "katago" not in ai_mode:
            game.katrain.log(f"Unknown AI mode {ai_mode} or policy missing, using default.", OUTPUT_INFO)
        aimove = Move.from_gtp(candidate_ai_moves[0]["move"], player=cn.next_player)
        game.katrain.log(f"Default strategy found {len(candidate_ai_moves)} moves and chose {aimove} as top move", OUTPUT_DEBUG)

    try:
        game.play(aimove)
    except IllegalMoveException as e:
        game.katrain.log(f"AI Strategy {ai_mode} generated illegal move {aimove}:  {e}", OUTPUT_ERROR)

    return aimove
