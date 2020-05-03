# This is a script that turns a KaTrain AI into a sort-of GTP compatible bot
import json
import sys
import time
import random

from core.ai import ai_move
from core.common import OUTPUT_ERROR, OUTPUT_INFO
from bots.settings import bot_strategy_names
from core.engine import EngineDiedException, KataGoEngine
from core.game import Game
from core.sgf_parser import Move

if len(sys.argv) < 2:
    bot = "dev"
else:
    bot = sys.argv[1].strip()
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8587
REPORT_SCORE_THRESHOLD = 1.5
MAX_WAIT_ANALYSIS = 10
MAX_PASS = 3  # after opponent passes this many times, we always pass


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
            msg = f"MALKOVICH:{cn.player} {cn.single_move.gtp()} caused a significant score change ({favpl} gained {abs(dscore):.1f} points)"
            if cn.ai_thoughts:
                msg += f" -> Win Rate {cn.format_win_rate()} Score {cn.format_score()} AI Thoughts: {cn.ai_thoughts}"
            else:
                comment = cn.comment(sgf=True).replace("\n", " ")
                msg += f" -> Detailed move analysis: {comment}"
            print(msg, file=sys.stderr)
            sys.stderr.flush()


while True:
    line = input()
    logger.log(f"GOT INPUT {line}", OUTPUT_ERROR)
    if "boardsize" in line:
        _, *size = line.strip().split(" ")
        if len(size) > 1:
            size = f"{size[0]}:{size[1]}"
        else:
            size = int(size[0])
        game = Game(Logger(), engine, {"init_size": size})
        logger.log(f"Init game {game.root.properties}", OUTPUT_ERROR)
    elif "komi" in line:
        _, komi = line.split(" ")
        game.root.set_property("KM", komi.strip())
        game.root.set_property("RU", "chinese")
        logger.log(f"Setting komi {game.root.properties}", OUTPUT_ERROR)
    elif "place_free_handicap" in line:
        _, n = line.split(" ")
        n = int(n)
        game.place_handicap_stones(n)
        handicaps = set(game.root.get_list_property("AB"))
        bx, by = game.board_size
        while len(handicaps) < min(n, bx * by):  # really obscure cases
            handicaps.add(Move((random.randint(0, bx - 1), random.randint(0, by - 1)), player="B").sgf(board_size=game.board_size))
        game.root.set_property("AB", list(handicaps))
        gtp = [Move.from_sgf(m, game.board_size, "B").gtp() for m in handicaps]
        logger.log(f"Chose handicap placements as {gtp}", OUTPUT_ERROR)
        print(f"= {' '.join(gtp)}\n")
        sys.stdout.flush()
        game.analyze_all_nodes()  # re-evaluate root
        continue
    elif "set_free_handicap" in line:
        _, *stones = line.split(" ")
        game.root.set_property("AB", [Move.from_gtp(move.upper()).sgf(game.board_size) for move in stones])
        logger.log(f"Set handicap placements to {game.root.get_list_property('AB')}", OUTPUT_ERROR)
    elif "genmove" in line:
        _, player = line.strip().split(" ")
        if player[0].upper() != game.next_player:
            logger.log(f"ERROR generating move: UNEXPECTED PLAYER {player} != {game.next_player}.", OUTPUT_ERROR)
            print(f"= ??\n")
            sys.stdout.flush()
            continue
        logger.log(f"{ai_strategy} generating move", OUTPUT_ERROR)
        game.current_node.analyze(engine)
        malkovich_analysis(game.current_node)
        game.root.properties[f"P{game.current_node.next_player}"] = [f"KaTrain {ai_strategy}"]
        num_passes = sum([int(n.is_pass or False) for n in game.current_node.nodes_from_root[::-1][0 : 2 * MAX_PASS : 2]])
        bx, by = game.board_size
        if num_passes >= MAX_PASS and game.current_node.depth - 2 * MAX_PASS >= bx + by:
            logger.log(f"Forced pass as opponent is passing {MAX_PASS} times", OUTPUT_ERROR)
            pol = game.current_node.policy
            if not pol:
                pol = ["??"]
            print(f"DISCUSSION:OK, since you passed {MAX_PASS} times after the {bx+by}th move, I will pass as well [policy {pol[-1]:.3%}].", file=sys.stderr)
            move = game.play(Move(None, player=game.next_player)).single_move
        else:
            move, node = ai_move(game, ai_strategy, ai_settings)
            if node is None:
                while node is None:
                    logger.log(f"ERROR generating move, backing up with weighted.", OUTPUT_ERROR)
                    move, node = ai_move(game, "p:weighted", {"pick_override": 1.0, "lower_bound": 0.001, "weaken_fac": 1})
            else:
                logger.log(f"Generated move {move}", OUTPUT_ERROR)
        print(f"= {move.gtp()}\n")
        sys.stdout.flush()
        malkovich_analysis(game.current_node)
        continue
    elif "play" in line:
        _, player, move = line.split(" ")
        node = game.play(Move.from_gtp(move.upper(), player=player[0].upper()), analyze=False)
        logger.log(f"played {player} {move}", OUTPUT_ERROR)
    elif "final_score" in line:
        score = game.current_node.format_score()
        game.game_id += f"_{score}"
        sgf = game.write_sgf("sgf_ogs/")
        logger.log(f"Game ended. Score was {score} -> saved sgf to {sgf}", OUTPUT_ERROR)
        print(f"= {score}\n")
        sys.stdout.flush()
        continue
    elif "quit" in line:
        print(f"= \n")
        break
    print(f"= \n")
    sys.stdout.flush()
