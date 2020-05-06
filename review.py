# This is a stand-alone script that generates a review for an SGF
import json
import sys
import time

from core.common import OUTPUT_INFO
from core.engine import KataGoEngine
from core.game import Game, KaTrainSGF

if len(sys.argv) < 2:
    exit(1)
inputfile = sys.argv[1]

with open("config.json") as f:
    settings = json.load(f)
    sgf_settings = settings["sgf"]
    engine_settings = settings["engine"]
    game_settings = settings["game"]
    trainer_settings = settings["trainer"]

engine_settings['threads'] = 16
#engine_settings['katago'] = 'KataGo/katago-bs'
engine_settings["max_time"] = 1000
engine_settings["max_visits"] = 50

class Logger:
    def log(self, msg, level):
        if level <= OUTPUT_INFO:
            print(msg)


logger = Logger()

engine = KataGoEngine(logger, engine_settings)
move_tree = KaTrainSGF.parse_file(inputfile)
game = Game(logger, engine, game_settings, move_tree=move_tree, analyze_fast=False)
nodes = game.root.nodes_in_tree
remaining = len(nodes)
while remaining > 0:
    remaining = sum(not n.analysis_ready for n in nodes)
    print(f"Waiting for {remaining} queries")
    time.sleep(0.1)

msg = game.write_sgf(
    sgf_settings["sgf_save"],
    trainer_config=trainer_settings,
    save_feedback=sgf_settings["save_feedback"],
    eval_thresholds=trainer_settings["eval_thresholds"],
)
