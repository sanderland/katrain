import json
import shlex
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

from constants import OUTPUT_DEBUG, OUTPUT_ERROR
from game_node import GameNode


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
        self.visits = [config["visits"], config["visits_fast"]]
        self.query_counter = 0
        self.katago_process = None
        self.base_priority = 0

        try:
            self.katrain.log(f"Starting KataGo with {self.command}", OUTPUT_DEBUG)
            self.katago_process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            self.analysis_thread = threading.Thread(target=self._analysis_read_thread, daemon=True).start()
        except FileNotFoundError:
            self.katrain.log(
                f"Starting kata with command '{self.command}' failed. If you are on Mac or Linux, please edit configuration file (config.json) to point to the correct KataGo executable.",
                OUTPUT_ERROR,
            )

    def on_new_game(self):
        self.base_priority += 1
        self.queries = {}

    def shutdown(self, finish=False):
        if finish:
            while self.queries:
                time.sleep(0.1)
        process = getattr(self, "katago_process")
        if process:
            process.terminate()
            self.katago_process = None

    def is_idle(self):
        return not self.queries

    def _analysis_read_thread(self):
        while True:
            line = self.katago_process.stdout.readline()
            if b"Uncaught exception" in line:
                self.katrain.log(f"KataGo Engine Failed: {line.decode()}", OUTPUT_ERROR)
            if not line:
                continue
            analysis = json.loads(line)
            if "error" in analysis:
                self.katrain.log(f"{analysis} received from KataGo", OUTPUT_ERROR)
            elif analysis["id"] in self.queries:
                callback, start_time = self.queries[analysis["id"]]
                time_taken = time.time() - start_time
                self.katrain.log(f"[{time_taken:.1f}][{analysis['id']}] KataGo Analysis Received: {analysis.keys()}   {line[:80]}...", OUTPUT_DEBUG)
                callback(analysis)
                del self.queries[analysis["id"]]
                self.katrain.update_state()
            else:
                self.katrain.log(f"Query result {analysis['id']} discarded -- recent new game?", OUTPUT_DEBUG)

    def request_analysis(self, analysis_node: GameNode, callback: Callable, faster: bool = False, min_visits: int = 0, priority: int = 0, ownership: Optional[bool] = None):
        fast = self.katrain.controls.ai_fast.active
        query_id = f"QUERY:{str(self.query_counter)}"
        self.query_counter += 1
        visits = self.config["visits_fast" if fast else "visits"]
        if faster:
            visits /= 5
        moves = [m for node in analysis_node.nodes_from_root for m in node.move_with_placements]

        if ownership is None:
            ownership = self.config["enable_ownership"]

        query = {
            "id": query_id,
            "rules": self.get_rules(analysis_node),
            "priority": self.base_priority + priority,
            "analyzeTurns": [len(moves)],
            "maxVisits": max(min_visits, visits),
            "komi": analysis_node.komi,
            "boardXSize": analysis_node.board_size,
            "boardYSize": analysis_node.board_size,
            "includeOwnership": ownership,
            "moves": [[m.player, m.gtp()] for m in moves],
        }
        self.queries[query_id] = (callback, time.time())
        if self.katago_process:
            self.katrain.log(f"Sending query {query_id}: {str(query)}", OUTPUT_DEBUG)
            self.katago_process.stdin.write((json.dumps(query) + "\n").encode())
            self.katago_process.stdin.flush()
