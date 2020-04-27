# This is a script that turns a KaTrain AI into a sort-of GTP compatible bot
import json
import time, sys
import traceback
from game import Game, Move
from ai import ai_move
from engine import KataGoEngine, EngineDiedException
from common import OUTPUT_ERROR, OUTPUT_INFO, OUTPUT_DEBUG, bot_strategy_names
from sgf_parser import Move

DB_FILENAME = "ai_performance.pickle"

if len(sys.argv) < 2:
    bot = "dev"
else:
    bot = sys.argv[1].strip()


class Logger:
    def log(self, msg, level):
        if level <= OUTPUT_INFO:
            print(msg, file=sys.stderr)


logger = Logger()

ENGINE_SETTINGS = {
    #    "katago": "../KataGo/cpp/katago",
    "katago": "python engine_connector.py 2222",  # actual engine settings in engine_server.py
    "model": "models/b15-1.3.2.txt.gz",
    "config": "KataGo/analysis_config.cfg",
    "max_visits": 5,
    "max_time": 5.0,
    "enable_ownership": False,
    "threads": 1,
}
ai_settings = {"noise_strength": 0.8, "pick_n": 10, "pick_frac": 0.2, "stddev": 10, "line_weight": 10, "pick_override": 0.95}

engine = KataGoEngine(logger, ENGINE_SETTINGS)

with open("config.json") as f:
    settings = json.load(f)
    all_ai_settings = settings["ai"]

all_ai_settings["dev"] = all_ai_settings["P:Noise"]

ai_strategy = bot_strategy_names[bot]
ai_settings = all_ai_settings[ai_strategy]


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
        game.root.set_property("KM", komi.strip())
        logger.log(f"Setting komi {game.root.properties}", OUTPUT_ERROR)
    elif "genmove" in line:
        logger.log(f"{ai_strategy} generating move", OUTPUT_ERROR)
        game.current_node.analyze(engine)
        game.root.properties[f"P{game.current_node.next_player}"] = [f"KaTrain {ai_strategy}"]
        move, node = ai_move(game, ai_strategy, ai_settings)
        print(f"= {move.gtp()}\n")
        sys.stdout.flush()
        cn = game.current_node
        logger.log(f"Waiting for analysis...", OUTPUT_ERROR)
        start = time.time()
        while not cn.analysis_ready:
            time.sleep(0.001)
            if engine.katago_process.poll() is not None:  # TODO: clean up
                raise EngineDiedException(f"Engine for {cn.next_player} ({engine.config}) died")
            if time.time() - start > 10:
                logger.log(f"Waiting for analysis timed out!", OUTPUT_ERROR)
                break
        if cn.analysis_ready:
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
