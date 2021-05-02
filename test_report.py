import os
import time

import pandas as pd
import numpy as np
from unidecode import unidecode

from katrain.core.ai import game_report
from katrain.core.base_katrain import KaTrainBase
from katrain.core.engine import KataGoEngine
from katrain.core.game import KaTrainSGF, Game
import matplotlib.pyplot as plt
pd.set_option('display.max_rows', 5000)

settings = {
    "fast_visits": 25,
    "visits": 500,
    "threads": 64,
    "model": "C:\\Users\\sande\\.katrain\\kata1-b40c256-s7907049728-d1917596640.bin.gz",
}
def dan(rank):
    rank=rank.lower()
    if rank[-1] in ['d','p']:
        return int(rank[:-1])
    elif rank=='?':
        return np.nan
    else:
        assert rank[-1]=='k', f"unexpected rank {rank}"
        return 1-int(rank[:-1])

katrain = KaTrainBase(force_package_config=True, debug_level=0)
engine = KataGoEngine(katrain, {**katrain.config("engine"), **settings})
thresholds = katrain.config("trainer/eval_thresholds")

games = []

for sgf in os.listdir("sgftest/"):
    if sgf.lower().endswith("sgf"):
        print(sgf)
        with open(os.path.join("sgftest", sgf)) as f:
            move_tree = KaTrainSGF.parse_sgf(f.read())
        games.append(Game(katrain, engine, move_tree=move_tree, analyze_fast=False))

while not engine.is_idle():
    print(f"waiting for engine to finish...{engine.queries_remaining()} queries left")
    time.sleep(0.5)
engine.shutdown(finish=None)

reports = []
for game in games:
    sum_stats, _, _ = game_report(game, thresholds=thresholds)
    for bw in "BW":
        oppbw = 'B' if bw=='W' else 'W'
        info = {f"name": game.root.get_property(f"P{bw}", "??"),
                "rank": game.root.get_property(f"{bw}R", "9p"),
                "opp_rank": game.root.get_property(f"{oppbw}R", "9p")
                }
        info["accuracy"] = sum_stats[bw][0]
        info["complexity"] = sum_stats[bw][1]
        info["mean point loss"] = sum_stats[bw][2]
        info["ai match rate"] = sum_stats[bw][3]
        reports.append(info)

df = pd.DataFrame(reports).sort_values(by="accuracy", ascending=False).reset_index(drop=True)
df.name = [unidecode(n) for n in df.name]
print(df)

df['numrank'] = [dan(rank) for rank in df['rank']]

plt.subplots(2,2)
plt.subplot(2,2,1)
plt.plot(df.numrank, df.accuracy,'kx')
plt.xlabel('dan')
plt.ylabel('accuracy')
plt.subplot(2,2,2)
plt.plot(df.numrank, df.complexity,'rx')
plt.xlabel('dan')
plt.ylabel('complexity')
plt.subplot(2,2,3)
plt.plot(df.numrank, df["mean point loss"],'gx')
plt.xlabel('dan')
plt.ylabel('mean point loss')
plt.subplot(2,2,4)
plt.plot(df.numrank, df["ai match rate"],'bx')
plt.xlabel('dan')
plt.ylabel('ai match rate')

plt.show()