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

pd.set_option("display.max_rows", 5000)

settings = {
    "fast_visits": 25,
    "max_visits": 500,
    "threads": 64,
    "model": "C:\\Users\\sande\\.katrain\\kata1-b40c256-s7907049728-d1917596640.bin.gz",
}
# settings["model"] = "C:\\Users\\sande\\.katrain\\g170e-b20c256x2-s5303129600-d1228401921.bin.gz"


def dan(rank):
    rank = rank.lower()
    if rank[-1] in ["d", "p"]:
        return int(rank[:-1])
    elif rank == "?":
        return np.nan
    else:
        assert rank[-1] == "k", f"unexpected rank {rank}"
        return 1 - int(rank[:-1])


def polyfit(x, y, degree=1):
    coeffs = np.polyfit(x, y, degree)
    correlation = np.corrcoef(x, y)[0, 1]
    results = {"coef": coeffs.tolist(), "r": correlation, "rsq": correlation**2}
    return results


katrain = KaTrainBase(force_package_config=True, debug_level=0)
combined_settings = {**katrain.config("engine"), **settings}
engine = KataGoEngine(katrain, {**katrain.config("engine"), **settings})
thresholds = katrain.config("trainer/eval_thresholds")

games = []
n = 0
for sgf in os.listdir("sgftest/"):
    if sgf.lower().endswith("sgf"):
        print(sgf)
        with open(os.path.join("sgftest", sgf)) as f:
            move_tree = KaTrainSGF.parse_sgf(f.read())
        games.append(Game(katrain, engine, move_tree=move_tree, analyze_fast=False))
    n += 1
    if n >= 30000:  # small test=3
        break

while not engine.is_idle():
    print(f"waiting for engine to finish...{engine.queries_remaining()} queries left")
    time.sleep(0.5)
engine.shutdown(finish=None)

reports = []
for game in games:
    sum_stats, _, _ = game_report(game, thresholds=thresholds)
    for bw in "BW":
        oppbw = "B" if bw == "W" else "W"
        info = {
            f"name": game.root.get_property(f"P{bw}", "??"),
            "rank": game.root.get_property(f"{bw}R", "9p"),
            "opp_rank": game.root.get_property(f"{oppbw}R", "9p"),
            **sum_stats[bw],
        }
        reports.append(info)

df = pd.DataFrame(reports).sort_values(by="accuracy", ascending=False).reset_index(drop=True)
df.name = [unidecode(n) for n in df.name]
print(df)

df["numrank"] = [dan(rank) for rank in df["rank"]]


def subplot(sp, ynames):
    global df
    plt.subplot(2, 2, sp)
    legend = []
    xfull = np.array(range(df["numrank"].min(), df["numrank"].max() + 1))
    cols = "bgr"
    for i, yname in enumerate(ynames):
        plt.plot(df["numrank"], df[yname], cols[i] + "x")
    for i, yname in enumerate(ynames):
        fit = polyfit(df["numrank"], df[yname])
        a, b = fit["coef"]
        plt.plot(xfull, xfull * a + b, cols[i] + ":")
        legend.append(f"{yname}: r^2 = {fit['rsq']:.3f}")
    plt.xlabel("dan rank")
    plt.legend(legend)


plt.subplots(2, 2)
subplot(1, ["accuracy"])
subplot(2, ["complexity"])
subplot(3, ["ai_top_move", "ai_top5_move"])
subplot(4, ["mean_ptloss", "weighted_ptloss"])
plt.show()
