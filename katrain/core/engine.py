import json
import shlex
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

from katrain.core.common import OUTPUT_DEBUG, OUTPUT_ERROR, OUTPUT_EXTRA_DEBUG, OUTPUT_KATAGO_STDERR, find_package_resource
from katrain.core.game_node import GameNode


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
        executable = config["katago"].strip()
        if not executable:
            if sys.platform.startswith("win"):
                executable = "katrain/KataGo/katago.exe"
            elif sys.platform.startswith("linux"):
                executable = "katrain/KataGo/katago"
            else:  # e.g. MacOS after brewing
                executable = "katago"

        modelfile, configfile, exefile = find_package_resource(config["model"]), find_package_resource(config["config"]), find_package_resource(executable)
        self.command = f'{exefile} analysis -model "{modelfile}" -config "{configfile}" -analysis-threads {config["threads"]}'
        if not sys.platform.startswith("win"):
            self.command = shlex.split(self.command)
        self.queries = {}  # outstanding query id -> start time and callback
        self.config = config
        self.query_counter = 0
        self.katago_process = None
        self.base_priority = 0
        self.override_settings = {}  # mainly for bot scripts to hook into
        self._lock = threading.Lock()
        self.analysis_thread = None
        self.stderr_thread = None
        self.start()

    def start(self):
        try:
            self.katrain.log(f"Starting KataGo with {self.command}", OUTPUT_DEBUG)
            self.katago_process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (FileNotFoundError, PermissionError, OSError) as e:
            if self.config["katago"].strip():
                self.katrain.log(
                    f"Starting kata with command '{self.command}' failed with error {e}. If on MacOS, see the manual on how to use brew to install katago first, and add it to your path or 'engine/katago' setting.",
                    OUTPUT_ERROR,
                )
            else:
                self.katrain.log(
                    f"Starting kata with command '{self.command}' failed with error {e}. Please make sure the 'katago' value under 'engine' in settings points to the correct KataGo executable.",
                    OUTPUT_ERROR,
                )
        self.analysis_thread = threading.Thread(target=self._analysis_read_thread, daemon=True).start()
        self.stderr_thread = threading.Thread(target=self._read_stderr_thread, daemon=True).start()

    def on_new_game(self):
        self.base_priority += 1
        self.queries = {}

    def restart(self):
        self.queries = {}
        self.shutdown(finish=False)
        self.start()

    def shutdown(self, finish=False):
        process = self.katago_process
        if finish and process:
            while self.queries and process.poll() is None:
                time.sleep(0.1)
        if process:
            process.terminate()
            self.katago_process = None
        if self.stderr_thread:
            self.stderr_thread.join()
        if self.analysis_thread:
            self.analysis_thread.join()

    def is_idle(self):
        return not self.queries

    def _read_stderr_thread(self):
        while self.katago_process is not None:
            try:
                line = self.katago_process.stderr.readline()
                if line:
                    self.katrain.log(line.decode().strip(), OUTPUT_KATAGO_STDERR)
            except:
                return

    def _analysis_read_thread(self):
        while self.katago_process is not None:
            try:
                line = self.katago_process.stdout.readline()
            except OSError as e:
                raise EngineDiedException(f"Engine died unexpectedly without sending output, possibly due to out of memory: {e}")
            if b"Uncaught exception" in line:
                self.katrain.log(f"KataGo Engine Failed: {line.decode()}", OUTPUT_ERROR)
                return
            if not line:
                continue
            analysis = json.loads(line)
            if analysis["id"] not in self.queries:
                self.katrain.log(f"Query result {analysis['id']} discarded -- recent new game?", OUTPUT_DEBUG)
                continue
            query_id = analysis["id"]
            callback, error_callback, start_time, next_move = self.queries[query_id]
            if "error" in analysis:
                del self.queries[query_id]
                if error_callback:
                    error_callback(analysis)
                elif not (next_move and "Illegal move" in analysis["error"]):  # sweep
                    self.katrain.log(f"{analysis} received from KataGo", OUTPUT_ERROR)
            elif "warning" in analysis:
                self.katrain.log(f"{analysis} received from KataGo", OUTPUT_DEBUG)
            else:
                del self.queries[query_id]
                time_taken = time.time() - start_time
                self.katrain.log(f"[{time_taken:.1f}][{analysis['id']}] KataGo Analysis Received: {analysis.keys()}", OUTPUT_DEBUG)
                self.katrain.log(line, OUTPUT_EXTRA_DEBUG)
                try:
                    callback(analysis)
                except Exception as e:
                    self.katrain.log(f"Error in engine callback for query {query_id}: {e}", OUTPUT_ERROR)
            if getattr(self.katrain, "update_state", None):  # easier mocking etc
                self.katrain.update_state()

    def send_query(self, query, callback, error_callback, next_move=None):
        with self._lock:
            self.query_counter += 1
            if "id" not in query:
                query["id"] = f"QUERY:{str(self.query_counter)}"
            self.queries[query["id"]] = (callback, error_callback, time.time(), next_move)
        if self.katago_process:
            self.katrain.log(f"Sending query {query['id']}: {json.dumps(query)}", OUTPUT_DEBUG)
            try:
                self.katago_process.stdin.write((json.dumps(query) + "\n").encode())
                self.katago_process.stdin.flush()
            except OSError as e:
                self.katrain.log(f"Engine died unexpectedly, possibly due to out of memory: {e}", OUTPUT_ERROR)
                return  # do not raise, since there's nothing to catch it

    def request_analysis(
        self,
        analysis_node: GameNode,
        callback: Callable,
        error_callback: Optional[Callable] = None,
        visits: int = None,
        analyze_fast: bool = False,
        time_limit=True,
        priority: int = 0,
        ownership: Optional[bool] = None,
        next_move=None,
    ):
        moves = [m for node in analysis_node.nodes_from_root for m in node.move_with_placements]
        if next_move:
            moves.append(next_move)
        if ownership is None:
            ownership = self.config["_enable_ownership"] and not next_move
        if visits is None:
            visits = self.config["max_visits"]
            if analyze_fast and self.config.get("fast_visits"):
                visits = self.config["fast_visits"]

        size_x, size_y = analysis_node.board_size
        settings = self.override_settings
        if time_limit:
            settings["maxTime"] = self.config["max_time"]
        if self.config.get("wide_root_noise", 0.0) > 0.0:  # don't send if 0.0, so older versions don't error
            settings["wideRootNoise"] = self.config["wide_root_noise"]

        query = {
            "rules": self.get_rules(analysis_node),
            "priority": self.base_priority + priority,
            "analyzeTurns": [len(moves)],
            "maxVisits": visits,
            "komi": analysis_node.komi,
            "boardXSize": size_x,
            "boardYSize": size_y,
            "includeOwnership": ownership,
            "includePolicy": not next_move,
            "moves": [[m.player, m.gtp()] for m in moves],
            "overrideSettings": settings,
        }
        self.send_query(query, callback, error_callback, next_move)
