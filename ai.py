import heapq
import math
import random
import time

import numpy as np

from common import OUTPUT_INFO, var_to_grid
from game import Move


def weighted_selection_without_replacement(items, m):
    """For a list of arrays where the first element is a weight, returns random items with those weights, without replacement."""
    elt = [(math.log(random.random()) / item[0], item) for item in items]
    return [e[1] for e in heapq.nlargest(m, elt)]  # NB fine if too small


def dirichlet_noise(num, dir_alpha=0.3):
    return np.random.dirichlet([dir_alpha] * num)


def ai_move(game, ai_settings):
    cn = game.current_node
    while not cn.analysis_ready:
        game.katrain.controls.set_status("Thinking...")  # TODO: non blocking somehow?
        time.sleep(0.01)
    # select move
    candidate_ai_moves = cn.candidate_moves
    ai_mode = game.katrain.controls.ai_mode(cn.next_player)

    if ("policy" in ai_mode or "p+" in ai_mode) and cn.policy:
        policy_moves = cn.policy_ranking
        size = game.board_size
        policy_grid = var_to_grid(cn.policy, size)
        legal_policy_moves = [(mv, pol) for mv, pol in policy_moves if not mv.is_pass if pol > 0]
        aimove = policy_moves[0][0]

        if not aimove.is_pass:
            if "noise" in ai_mode:
                noise_str = ai_settings["noise_strength"]
                d_noise = dirichlet_noise(len(legal_policy_moves))
                noisy_policy_moves = [(mv, (1 - noise_str) * pol + noise_str * noise) for ((mv, pol), noise) in zip(legal_policy_moves, d_noise)]
                aimove = max(noisy_policy_moves, key=lambda mp: mp[1])[0]
            if "local" in ai_mode or "tenuki" in ai_mode or "pick" in ai_mode and cn.single_move and cn.single_move.coords:
                var = ai_settings["local_stddev"] ** 2
                n_moves = int(ai_settings["pick_frac"] * len(legal_policy_moves) + ai_settings["pick_n"])
                mx, my = cn.single_move.coords
                top_5_pass = any([polmove[0].is_pass for polmove in policy_moves[:5]])  # dont make it jump around for the last few sensible non pass moves
                if not top_5_pass:
                    if "local" in ai_mode:
                        weighted_coords = [
                            (math.exp(-0.5 * ((x - mx) ** 2 + (y - my) ** 2) / var), x, y, policy_grid[y][x])
                            for x in range(size[0])
                            for y in range(size[1])
                            if policy_grid[y][x] > 0
                        ]
                    else:  # if "pick" in ai_mode -> even
                        weighted_coords = [(1, x, y, policy_grid[y][x]) for x in range(size[0]) for y in range(size[1]) if policy_grid[y][x] > 0]
                    pick_moves = weighted_selection_without_replacement(weighted_coords, n_moves)
                    if pick_moves:
                        best = max(pick_moves, key=lambda m: m[3])
                        aimove = Move((best[1], best[2]), player=cn.next_player)
                        game.katrain.log(
                            f"{aimove} was top from pick moves starting with {[Move((best[1], best[2]), player=cn.next_player).gtp() for best in pick_moves[:10]]} out of {len(pick_moves)} "
                        )
                    else:
                        aimove = Move(None, player=cn.next_player)  # pass
                else:
                    weighted_coords = [(policy_grid[y][x], x, y, policy_grid[y][x]) for x in range(size[0]) for y in range(size[1]) if policy_grid[y][x] > 0]
                    aimove = Move(weighted_selection_without_replacement(weighted_coords, 1)[0][1:3], player=cn.next_player)  # just take a random move by policy w/o noise
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
    elif "jigo" in ai_mode and candidate_ai_moves[0]["move"] != "pass":
        sign = cn.player_sign(cn.next_player)  # TODO check
        jigo_move = min(candidate_ai_moves, key=lambda move: abs(sign * move["scoreLead"] - 0.5))
        aimove = Move.from_gtp(jigo_move["move"], player=cn.next_player)
    else:
        if "default" not in ai_mode:
            game.katrain.log(f"Unknown AI mode {ai_mode} or policy missing, using default.", OUTPUT_INFO)
        aimove = Move.from_gtp(candidate_ai_moves[0]["move"], player=cn.next_player)
    print("COORDS", aimove.coords)
    game.play(aimove)
