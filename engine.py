import json
import shlex
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

from common import OUTPUT_DEBUG, OUTPUT_ERROR, OUTPUT_EXTRA_DEBUG
from game_node import GameNode


class EngineDiedException(Exception):
    pass


class KataGoEngine:
    """Starts and communicates with the KataGO analysis engine"""

    # TODO: we don't support suicide in game.py, so no  "tt": "tromp-taylor", "nz": "new-zealand"
    RULESETS = {"jp": "japanese", "cn": "chinese", "ko": "korean", "aga": "aga"}
    RULESETS.update({v: v for v in RULESETS.values()})

    @staticmethod
    def get_rules(node):
        return KataGoEngine.RULESETS.get(str(node.ruleset).lower(), "japanese")

    def __init__(self, katrain, config):
        self.katrain = katrain
        self.command = f"{config['katago']} analysis -model {config['model']} -config {config['config']} -analysis-threads {config['threads']}"
        if "win" not in sys.platform:
            self.command = shlex.split(self.command)
        self.queries = {}  # outstanding query id -> start time and callback
        self.config = config
        self.query_counter = 0
        self.katago_process = None
        self.base_priority = 0
        self._lock = threading.Lock()

        try:
            self.katrain.log(f"Starting KataGo with {self.command}", OUTPUT_DEBUG)
            self.katago_process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            self.analysis_thread = threading.Thread(target=self._analysis_read_thread, daemon=True).start()
        except FileNotFoundError:
            self.katrain.log(
                f"Starting kata with command '{self.command}' failed. If you are on Mac or Linux, please change the settings or configuration file (config.json) to point to the correct KataGo executable.",
                OUTPUT_ERROR,
            )

    def on_new_game(self):
        self.base_priority += 1
        self.queries = {}

    def shutdown(self, finish=False):
        process = getattr(self, "katago_process", None)
        if finish and process:
            while self.queries and process.poll() is None:
                time.sleep(0.1)
        if process:
            process.terminate()
            self.katago_process = None

    def is_idle(self):
        return not self.queries

    def _analysis_read_thread(self):
        while self.katago_process is not None:
            try:
                line = self.katago_process.stdout.readline()
            except OSError as e:
                raise EngineDiedException(f"Engine died unexpectedly without sending output, possibly due to out of memory: {e}")
            if b"Uncaught exception" in line:
                self.katrain.log(f"KataGo Engine Failed: {line.decode()}", OUTPUT_ERROR)
            if not line:
                continue
            analysis = json.loads(line)
            if analysis["id"] in self.queries:
                callback, start_time, next_move = self.queries[analysis["id"]]
            else:
                self.katrain.log(f"Query result {analysis['id']} discarded -- recent new game?", OUTPUT_DEBUG)
                continue
            if "error" in analysis:
                if not (next_move is None and "Illegal move" in analysis["error"]):  # sweep
                    self.katrain.log(f"{analysis} received from KataGo", OUTPUT_ERROR)
                continue
            else:
                callback, start_time, next_move = self.queries[analysis["id"]]
                time_taken = time.time() - start_time
                self.katrain.log(f"[{time_taken:.1f}][{analysis['id']}] KataGo Analysis Received: {analysis.keys()}   {line[:80]}...", OUTPUT_EXTRA_DEBUG)
                callback(analysis)
                del self.queries[analysis["id"]]
                if getattr(self.katrain, "update_state", None):  # easier mocking etc
                    self.katrain.update_state()

    def send_query(self, query, callback, next_move):
        with self._lock:
            self.query_counter += 1
            if "id" not in query:
                query["id"] = f"QUERY:{str(self.query_counter)}"
            self.queries[query["id"]] = (callback, time.time(), next_move)
        if self.katago_process:
            self.katrain.log(f"Sending query {query['id']}: {str(query)}", OUTPUT_EXTRA_DEBUG)
            try:
                self.katago_process.stdin.write((json.dumps(query) + "\n").encode())
                self.katago_process.stdin.flush()
            except OSError as e:
                self.katrain.log(f"Engine died unexpectedly, possibly due to out of memory: {e}", OUTPUT_ERROR)
                return  # do not raise, since

    def request_analysis(
        self, analysis_node: GameNode, callback: Callable, visits: int = None, time_limit=True, priority: int = 0, ownership: Optional[bool] = None, next_move=None
    ):
        moves = [m for node in analysis_node.nodes_from_root for m in node.move_with_placements]
        if next_move:
            moves.append(next_move)
        if ownership is None:
            ownership = self.config["enable_ownership"] and not next_move
        size_x, size_y = analysis_node.board_size
        query = {
            "rules": self.get_rules(analysis_node),
            "priority": self.base_priority + priority,
            "analyzeTurns": [len(moves)],
            "maxVisits": visits or self.config["max_visits"],
            "komi": analysis_node.komi,
            "boardXSize": size_x,
            "boardYSize": size_y,
            "includeOwnership": ownership,
            "includePolicy": not next_move,
            "moves": [[m.player, m.gtp()] for m in moves],
            "overrideSettings": {"maxTime": self.config["max_time"] if time_limit else 1000.0}
            # "overrideSettings": {"playoutDoublingAdvantage": 3.0, "playoutDoublingAdvantagePla":  'BLACK' if not moves or moves[-1].player == 'W' else "WHITE"}
        }
        self.send_query(query, callback, next_move)
