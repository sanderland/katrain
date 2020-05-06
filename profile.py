# This is a stand-alone script that generates a review for an SGF
import json
import sys
import time

from core.common import OUTPUT_INFO
from core.engine import KataGoEngine
from core.game import Game, KaTrainSGF

start = time.time()
if len(sys.argv) < 2:
    exit(1)
inputfile = sys.argv[1]

with open("config.json") as f:
    settings = json.load(f)
    sgf_settings = settings["sgf"]
    engine_settings = settings["engine"]
    game_settings = settings["game"]
    trainer_settings = settings["trainer"]

# engine_settings['threads'] = 32
engine_settings["max_time"] = 1000


class Logger:
    def log(self, msg, level):
        if level <= OUTPUT_INFO:
            print(msg)


logger = Logger()

engine = KataGoEngine(logger, engine_settings)
move_tree = KaTrainSGF.parse_file(inputfile)
game = Game(logger, engine, game_settings, move_tree=None, analyze_fast=True)
game.root = move_tree
reverse_nodes = game.root.nodes_in_tree[::-1]

for n in reverse_nodes[::10]:
    n.analyze(engine=engine)
    while not n.analysis_ready:
        time.sleep(0.01)
    print(n.single_move, "done")

print(time.time() - start, "s")
