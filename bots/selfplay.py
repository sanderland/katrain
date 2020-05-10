# This is a script I use to test the performance of AIs
import pickle
import sys
import threading
import time
import traceback
from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor

from core.ai import ai_move
from core.common import OUTPUT_ERROR, OUTPUT_INFO
from elote import EloCompetitor
from core.engine import KataGoEngine
from core.game import Game
import json

DB_FILENAME = "bots/ai_performance.pickle"


class Logger:
    def log(self, msg, level):
        if level <= OUTPUT_INFO:
            print(msg)
        if level <= OUTPUT_ERROR:
            print(msg, file=sys.stderr)


logger = Logger()

with open("config.json") as f:
    settings = json.load(f)
    DEFAULT_AI_SETTINGS = settings["ai"]


class AI:
    DEFAULT_ENGINE_SETTINGS = {
        "katago": "KataGo/katago",
        "model": "KataGo/models/b15-1.3.2.txt.gz",
        "config": "KataGo/analysis_config.cfg",
        "max_visits": 1,
        "max_time": 300.0,
        "_enable_ownership": False,
    }
    NUM_THREADS = 32
    IGNORE_SETTINGS_IN_TAG = {"threads", "_enable_ownership", "katago"}  # katago for switching from/to bs version
    ENGINES = []
    LOCK = threading.Lock()

    def __init__(self, strategy, ai_settings, engine_settings=None):
        self.elo_comp = EloCompetitor(initial_rating=1000)
        self.strategy = strategy
        self.ai_settings = ai_settings
        self.engine_settings = engine_settings or {}
        fmt_settings = [f"{k}={v}" for k, v in {**self.ai_settings, **self.engine_settings}.items() if k not in AI.IGNORE_SETTINGS_IN_TAG]
        self.name = f"{strategy}({ ','.join(fmt_settings) })"
        self.fix_settings()

    def fix_settings(self):
        self.ai_settings = {**DEFAULT_AI_SETTINGS[self.strategy], **self.ai_settings}
        self.engine_settings = {**AI.DEFAULT_ENGINE_SETTINGS, **self.engine_settings, "threads": AI.NUM_THREADS}

    def get_engine(self):  # factory
        with AI.LOCK:
            for existing_engine_settings, engine in AI.ENGINES:
                if existing_engine_settings == self.engine_settings:
                    return engine
            engine = KataGoEngine(logger, self.engine_settings)
            AI.ENGINES.append((self.engine_settings, engine))
            print("Creating new engine for", self.engine_settings, "now have", len(AI.ENGINES), "engines up")
            return engine

    def __eq__(self, other):
        return self.name == other.name  # should capture all relevant setting differences


try:
    with open(DB_FILENAME, "rb") as f:
        ai_database, all_results = pickle.load(f)
        for ai in ai_database:
            ai.fix_settings()  # update as required
except FileNotFoundError:
    ai_database = []
    all_results = []


def add_ai(ai):
    if ai not in ai_database:
        ai_database.append(ai)
        print(f"Adding {ai.name}")
    else:
        print(f"AI {ai.name} already in DB")


def retrieve_ais(selected_ais):
    return [ai for ai in ai_database if ai in selected_ais]


test_ais = [
    #  AI("Jigo", {}, {"max_visits": 100}),
    AI("Policy", {}, {"model": "my/model.bin.gz"}),
    AI("Policy", {}, {"model": "KataGo/models/b10-1.3.txt.gz"}),
    AI("Policy", {}),
    AI("P:Local", {}),
    AI("P:Pick", {}),
    AI("P:Noise", {}),
    AI("P:Tenuki", {}),
    AI("P:Local", {}),
    AI("P:Influence", {}),
    AI("P:Territory", {}),
    AI("P:Weighted", {}),
]


for ai in test_ais:
    add_ai(ai)

N_GAMES = 5
BOARDSIZE = 19

ais_to_test = retrieve_ais(test_ais)

results = defaultdict(list)


def play_games(black: AI, white: AI):
    players = {"B": black, "W": white}
    engines = {"B": black.get_engine(), "W": white.get_engine()}
    tag = f"{black.name} vs {white.name}"
    try:
        game = Game(Logger(), engines, {"init_size": BOARDSIZE})
        game.root.add_list_property("PW", [white.name])
        game.root.add_list_property("PB", [black.name])
        start_time = time.time()
        while not game.ended:
            p = game.current_node.next_player
            move = ai_move(game, players[p].strategy, players[p].ai_settings)
        while not game.current_node.analysis_ready:
            time.sleep(0.001)
        game.game_id += f"_{game.current_node.format_score()}"
        print(f"{tag}\tGame finished in {time.time()-start_time:.1f}s  {game.current_node.format_score()} -> {game.write_sgf('sgf_selfplay/')}", file=sys.stderr)
        score = game.current_node.score
        if score > 0.3:
            black.elo_comp.beat(white.elo_comp)
        elif score > -0.3:
            black.elo_comp.tied(white.elo_comp)

        results[tag].append(score)
        all_results.append((black.name, white.name, score))

    except Exception as e:
        print(f"Exception in playing {tag}: {e}")
        print(f"Exception in playing {tag}: {e}", file=sys.stderr)
        traceback.print_exc()
        traceback.print_exc(file=sys.stderr)


def fmt_score(score):
    return f"{'B' if score >= 0 else 'W'}+{abs(score):.1f}"


print(len(ais_to_test), "ais to test")
global_start = time.time()

for n in range(N_GAMES):
    for _, e in AI.ENGINES:  # no caching/replays
        e.shutdown()
    AI.ENGINES = []

    with ThreadPoolExecutor(max_workers=16) as threadpool:
        for b in ais_to_test:
            for w in ais_to_test:
                if b is not w:
                    threadpool.submit(play_games, b, w)
    print("POOL EXIT")

    print(f"---- RESULTS ({n}) ----")
    for k, v in results.items():
        b_win = sum([s > 0.3 for s in v])
        w_win = sum([s < -0.3 for s in v])
        print(f"{b_win} {k} {w_win} : {list(map(fmt_score,v))}")

    print("---- ELO ----")
    for ai in sorted(ai_database, key=lambda a: -a.elo_comp.rating):
        wins = [(b, w, s) for (b, w, s) in all_results if s > 0.3 and b == ai.name or w == ai.name and s < -0.3]
        losses = [(b, w, s) for (b, w, s) in all_results if s < -0.3 and b == ai.name or w == ai.name and s > -0.3]
        draws = [(b, w, s) for (b, w, s) in all_results if -0.3 <= s <= 0.3 and (b == ai.name or w == ai.name)]
        out = f"{'*' if ai in ais_to_test else ' '} {ai.name}: ELO {ai.elo_comp.rating:.1f} WINS {len(wins)} LOSSES {len(losses)} DRAWS {len(draws)}"
        #    print("Wins:",wins)
        print(out)
        print(out, file=sys.stderr)

    with open(DB_FILENAME, "wb") as f:
        pickle.dump((ai_database, all_results), f)
    print(f"Saving {len(all_results)} to pickle", file=sys.stderr)

print(f"Done!Time taken {time.time()-global_start:.1f}s", file=sys.stderr)
