# This is a script that turns a KaTrain AI into a sort-of GTP compatible bot
import json
import sys
import time

from ai import ai_move
from common import OUTPUT_DEBUG, OUTPUT_ERROR, OUTPUT_INFO
from bots.settings import bot_strategy_names
from engine import EngineDiedException, KataGoEngine
from game import Game, Move
from sgf_parser import Move

if len(sys.argv) < 2:
    bot = "dev"
else:
    bot = sys.argv[1].strip()
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8587
REPORT_SCORE_THRESHOLD = 1.5
MAX_WAIT_ANALYSIS = 10


class Logger:
    def log(self, msg, level):
        if level <= OUTPUT_INFO:
            print(msg, file=sys.stderr)


logger = Logger()


ENGINE_SETTINGS = {
    "katago": f"python bots/engine_connector.py {port}",  # actual engine settings in engine_server.py
    "model": "models/b15-1.3.2.txt.gz",
    "config": "KataGo/analysis_config.cfg",
    "max_visits": 5,
    "max_time": 5.0,
    "_enable_ownership": False,
    "threads": 1,
}


engine = KataGoEngine(logger, ENGINE_SETTINGS)

with open("config.json") as f:
    settings = json.load(f)
    all_ai_settings = settings["ai"]

all_ai_settings["dev"] = all_ai_settings["P:Noise"]

ai_strategy = bot_strategy_names[bot]
ai_settings = all_ai_settings[ai_strategy]

print(f"starting bot {bot} using server port {port}", file=sys.stderr)
print(ENGINE_SETTINGS, file=sys.stderr)
print(ai_strategy, ai_settings, file=sys.stderr)

logger.log(f"STARTED ENGINE", OUTPUT_ERROR)

game = Game(Logger(), engine, {})


def malkovich_analysis(cn):
    start = time.time()
    while not cn.analysis_ready:
        time.sleep(0.001)
        if engine.katago_process.poll() is not None:  # TODO: clean up
            raise EngineDiedException(f"Engine for {cn.next_player} ({engine.config}) died")
        if time.time() - start > MAX_WAIT_ANALYSIS:
            logger.log(f"Waiting for analysis timed out!", OUTPUT_ERROR)
            return
    if cn.analysis_ready and cn.parent and cn.parent.analysis_ready:
        dscore = cn.analysis["root"]["scoreLead"] - cn.parent.analysis["root"]["scoreLead"]
        logger.log(f"dscore {dscore} = {cn.analysis['root']['scoreLead']} {cn.parent.analysis['root']['scoreLead']} at {move}...", OUTPUT_ERROR)
        if abs(dscore) > REPORT_SCORE_THRESHOLD and (cn.player == "B" and dscore < 0 or cn.player == "W" and dscore > 0):  # relevant mistakes
            favpl = "B" if dscore > 0 else "W"
            msg = f"MALKOVICH:{cn.player} {cn.single_move.gtp()} caused a significant score change ({favpl} gained {abs(dscore):.1f} points) -> Win Rate {cn.format_win_rate()} Expected Score {cn.format_score()}"
            if cn.ai_thoughts:
                msg += f" AI Thoughts: {cn.ai_thoughts}"
            print(msg, file=sys.stderr)
            sys.stderr.flush()


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
        malkovich_analysis(game.current_node)
        game.root.properties[f"P{game.current_node.next_player}"] = [f"KaTrain {ai_strategy}"]
        move, node = ai_move(game, ai_strategy, ai_settings)
        print(f"= {move.gtp()}\n")
        sys.stdout.flush()
        malkovich_analysis(game.current_node)
        continue
    elif "play" in line:
        _, player, move = line.split(" ")
        node = game.play(Move.from_gtp(move.upper(), player=player[0].upper()), analyze=False)
        logger.log(f"played {player} {move}", OUTPUT_ERROR)
    print(f"= \n")

game.game_id += f"_{game.current_node.format_score()}"
game.write_sgf("sgf_ogs/")
