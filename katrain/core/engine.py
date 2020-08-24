import copy
import json
import os
import subprocess
import threading
import time
import traceback
from typing import Callable, Dict, Optional

from kivy.utils import platform

from katrain.core.constants import OUTPUT_DEBUG, OUTPUT_ERROR, OUTPUT_EXTRA_DEBUG, OUTPUT_KATAGO_STDERR
from katrain.core.game_node import GameNode
from katrain.core.lang import i18n
from katrain.core.utils import find_package_resource


class EngineDiedException(Exception):
    pass


class KataGoEngine:
    """Starts and communicates with the KataGO analysis engine"""

    # TODO: we don't support suicide in game.py, so no  "tt": "tromp-taylor", "nz": "new-zealand"
    RULESETS_ABBR = [("jp", "japanese"), ("cn", "chinese"), ("ko", "korean"), ("aga", "aga")]
    RULESETS = {fromkey: name for abbr, name in RULESETS_ABBR for fromkey in [abbr, name]}

    @staticmethod
    def get_rules(node):
        return KataGoEngine.RULESETS.get(str(node.ruleset).lower(), "japanese")

    def __init__(self, katrain, config):
        self.katrain = katrain
        self.queries = {}  # outstanding query id -> start time and callback
        self.config = config
        self.query_counter = 0
        self.katago_process = None
        self.base_priority = 0
        self.override_settings = {"reportAnalysisWinratesAs": "BLACK"}  # force these settings
        self._lock = threading.Lock()
        self.analysis_thread = None
        self.stderr_thread = None

        exe = config.get("katago", "").strip()
        if config.get("altcommand", ""):
            self.command = config["altcommand"]
        else:
            if not exe:
                if platform == "win":
                    exe = "katrain/KataGo/katago.exe"
                elif platform == "linux":
                    exe = "katrain/KataGo/katago"
                else:  # e.g. MacOS after brewing
                    exe = "katago"

            model = find_package_resource(config["model"])
            cfg = find_package_resource(config["config"])
            if exe.startswith("katrain"):
                exe = find_package_resource(exe)

            exepath, exename = os.path.split(exe)
            if exepath and not os.path.isfile(exe):
                self.katrain.log(i18n._("Kata exe not found").format(exe=exe), OUTPUT_ERROR)
                return  # don't start
            elif not exepath and not any(
                os.path.isfile(os.path.join(path, exe)) for path in os.environ.get("PATH", "").split(os.pathsep)
            ):
                self.katrain.log(i18n._("Kata exe not found in path").format(exe=exe), OUTPUT_ERROR)
                return  # don't start
            elif not os.path.isfile(model):
                self.katrain.log(i18n._("Kata model not found").format(model=model), OUTPUT_ERROR)
                return  # don't start
            elif not os.path.isfile(cfg):
                self.katrain.log(i18n._("Kata config not found").format(config=cfg), OUTPUT_ERROR)
                return  # don't start
            self.command = f'"{exe}" analysis -model "{model}" -config "{cfg}" -analysis-threads {config["threads"]}'
        self.start()

    def start(self):
        try:
            self.katrain.log(f"Starting KataGo with {self.command}", OUTPUT_DEBUG)
            self.katago_process = subprocess.Popen(
                self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True
            )
        except (FileNotFoundError, PermissionError, OSError) as e:
            self.katrain.log(
                i18n._("Starting Kata failed").format(command=self.command, error=e), OUTPUT_ERROR,
            )
            return  # don't start
        self.analysis_thread = threading.Thread(target=self._analysis_read_thread, daemon=True).start()
        self.stderr_thread = threading.Thread(target=self._read_stderr_thread, daemon=True).start()

    def on_new_game(self):
        self.base_priority += 1
        self.queries = {}

    def restart(self):
        self.queries = {}
        self.shutdown(finish=False)
        self.start()

    def check_alive(self, os_error="", exception_if_dead=False):
        ok = self.katago_process and self.katago_process.poll() is None
        if not ok and exception_if_dead:
            if self.katago_process:
                code = self.katago_process and self.katago_process.poll()
                if code == 3221225781:
                    died_msg = i18n._("Engine missing DLL")
                else:
                    os_error += f"status {code}"
                    died_msg = i18n._("Engine died unexpectedly").format(error=os_error)
                self.katrain.log(died_msg, OUTPUT_ERROR)
                self.katago_process = None
            else:
                died_msg = i18n._("Engine died unexpectedly").format(error=os_error)
            raise EngineDiedException(died_msg)
        return ok

    def shutdown(self, finish=False):
        process = self.katago_process
        if finish and process:
            while self.queries and process.poll() is None:
                time.sleep(0.1)
        if process:
            self.katago_process = None
            process.terminate()
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
                    try:
                        self.katrain.log(line.decode(errors="ignore").strip(), OUTPUT_KATAGO_STDERR)
                    except Exception as e:
                        print("ERROR in processing KataGo stderr:", line, "Exception", e)
                elif self.katago_process:
                    self.check_alive(exception_if_dead=True)
            except Exception as e:
                self.katrain.log(f"Exception in reading stdout {e}", OUTPUT_DEBUG)
                return

    def _analysis_read_thread(self):
        while self.katago_process is not None:
            try:
                line = self.katago_process.stdout.readline().strip()
                if self.katago_process and not line:
                    self.check_alive(exception_if_dead=True)
            except OSError as e:
                self.check_alive(os_error=str(e), exception_if_dead=True)
                return

            if b"Uncaught exception" in line:
                self.katrain.log(f"KataGo Engine Failed: {line.decode(errors='ignore')}", OUTPUT_ERROR)
                return
            if not line:
                continue
            try:
                analysis = json.loads(line)
                if "id" not in analysis:
                    self.katrain.log(f"Error without ID {analysis} received from KataGo", OUTPUT_ERROR)
                    continue
                query_id = analysis["id"]
                if query_id not in self.queries:
                    self.katrain.log(f"Query result {query_id} discarded -- recent new game?", OUTPUT_DEBUG)
                    continue
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
                    self.katrain.log(
                        f"[{time_taken:.1f}][{query_id}] KataGo Analysis Received: {analysis.keys()}", OUTPUT_DEBUG,
                    )
                    self.katrain.log(line, OUTPUT_EXTRA_DEBUG)
                    try:
                        callback(analysis)
                    except Exception as e:
                        self.katrain.log(f"Error in engine callback for query {query_id}: {e}", OUTPUT_ERROR)
                if getattr(self.katrain, "update_state", None):  # easier mocking etc
                    self.katrain.update_state()
            except Exception as e:
                self.katrain.log(f"Unexpected exception {e} while processing KataGo output {line}", OUTPUT_ERROR)
                traceback.print_exc()

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
                self.check_alive(os_error=str(e), exception_if_dead=True)
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
        next_move: Optional[GameNode] = None,
        extra_settings: Optional[Dict] = None,
    ):
        moves = [m for node in analysis_node.nodes_from_root for m in node.moves]
        initial_stones = analysis_node.root.placements
        if next_move:
            moves.append(next_move)
        if ownership is None:
            ownership = self.config["_enable_ownership"] and not next_move
        if visits is None:
            visits = self.config["max_visits"]
            if analyze_fast and self.config.get("fast_visits"):
                visits = self.config["fast_visits"]

        size_x, size_y = analysis_node.board_size
        settings = copy.copy(self.override_settings)
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
            "includeOwnership": ownership and not next_move,
            "includePolicy": not next_move,
            "initialStones": [[m.player, m.gtp()] for m in initial_stones],
            "moves": [[m.player, m.gtp()] for m in moves],
            "overrideSettings": {**settings, **(extra_settings or {})},
        }
        self.send_query(query, callback, error_callback, next_move)
        analysis_node.analysis_visits_requested = max(analysis_node.analysis_visits_requested, visits)
