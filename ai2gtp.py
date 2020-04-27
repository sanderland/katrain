# This is a script that turns a KaTrain AI into a sort-of GTP compatible bot
import time, sys
import traceback
from game import Game, Move
from ai import ai_move
from engine import KataGoEngine
from common import OUTPUT_ERROR, OUTPUT_INFO, OUTPUT_DEBUG
from sgf_parser import Move

DB_FILENAME = "ai_performance.pickle"


class Logger:
    def log(self, msg, level):
        if level <= OUTPUT_DEBUG:
            print(msg, file=sys.stderr)


logger = Logger()

ENGINE_SETTINGS = {
    "katago": "../KataGo/cpp/katago",
    "model": " models/b15-1.3.2.txt.gz",
    "config": "KataGo/analysis_config.cfg",
    "max_visits": 5,
    "max_time": 5.0,
    "enable_ownership": False,
    "threads": 1,
}
ai_settings = {"noise_strength": 0.8, "pick_n": 10, "pick_frac": 0.2, "stddev": 10, "line_weight": 10, "pick_override": 0.95}

engine = KataGoEngine(logger, ENGINE_SETTINGS)

ai_strategy = "P+Influence"
ai_settings["pick_frac"] = 0.5
ai_settings["line_weight"] = 10

ai_strategy = "P+Local"
ai_settings["pick_frac"] = 0.0
ai_settings["pick_n"] = 20
ai_settings["stddev"] = 1.5

ai_strategy = "P+Pick"
ai_settings["pick_frac"] = 0.33  # dropping below 7k
ai_settings["pick_n"] = 5  # dropping below 7k at 5/0.33

ai_strategy = "P+Weighted"
ai_settings = {"pick_override": 0.95}


logger.log(f"STARTED ENGINE", OUTPUT_ERROR)

game = Game(Logger(), engine, {})

while not game.ended:
    p = game.current_node.next_player
    line = input()
    logger.log(f"GOT INPUT {line}", OUTPUT_ERROR)
    if "boardsize" in line:
        _, size = line.split(" ")
        game = Game(Logger(), engine, {"init_size": int(size)})
        logger.log(f"Init game {game.root.properties}", OUTPUT_ERROR)
    if "komi" in line:
        _, komi = line.split(" ")
        game.root.properties["KM"] = [komi.strip()]
        logger.log(f"Setting komi {game.root.properties}", OUTPUT_ERROR)
    elif "genmove" in line:
        game.current_node.analyze(engine)
        game.root.properties[f"P{game.current_node.next_player}"] = [f"KaTrain {ai_strategy}"]
        move, node = ai_move(game, ai_strategy, ai_settings)
        logger.log(f"SENT TO GTP: = {move.gtp()}", OUTPUT_ERROR)
        print(f"= {move.gtp()}\n")
        sys.stdout.flush()
        cn = game.current_node
        while not cn.analysis_ready:
            time.sleep(0.001)
        pv = ""
        moves = sorted(list(cn.analysis["moves"].values()), key=lambda d: d["order"])
        if moves:
            pv = " ".join(moves[0]["pv"])
        print(
            f"CHAT:Visits {cn.ai_thoughts} Winrate {cn.analysis['root']['winrate']:.2%} ScoreLead {cn.analysis['root']['scoreLead']:.1f} ScoreStdev 0.0 PV {move.gtp()} {pv}",
            file=sys.stderr,
        )
        continue
    elif "play" in line:
        _, player, move = line.split(" ")
        node = game.play(Move.from_gtp(move.upper(), player=player[0].upper()), analyze=False)
        logger.log(f"played {player} {move}", OUTPUT_ERROR)
    print(f"= \n")

game.game_id += f"_{game.current_node.format_score()}"
game.write_sgf("sgf_ogs/")
