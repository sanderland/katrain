import copy
import json
import os
import queue
import shlex
import subprocess
import threading
import time
import traceback
from typing import Callable, Dict, List, Optional

from kivy.utils import platform

from katrain.core.constants import OUTPUT_DEBUG, OUTPUT_ERROR, OUTPUT_EXTRA_DEBUG, OUTPUT_KATAGO_STDERR
from katrain.core.game_node import GameNode
from katrain.core.lang import i18n
from katrain.core.sgf_parser import Move
from katrain.core.utils import find_package_resource, json_truncate_arrays


class EngineDiedException(Exception):
    pass


class KataGoEngine:
    """Starts and communicates with the KataGO analysis engine"""

    # TODO: we don't support suicide in game.py, so no  "tt": "tromp-taylor", "nz": "new-zealand"
    RULESETS_ABBR = [
        ("jp", "japanese"),
        ("cn", "chinese"),
        ("ko", "korean"),
        ("aga", "aga"),
        ("stone_scoring", "stone_scoring"),
    ]
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
        self.analysis_thread = None
        self.stderr_thread = None
        self.write_stdin_thread = None
        self.shell = False
        self.write_queue = queue.Queue()
        self.thread_lock = threading.Lock()
        exe = config.get("katago", "").strip()
        if config.get("altcommand", ""):
            self.command = config["altcommand"]
            self.shell = True
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
            self.command = shlex.split(
                f'"{exe}" analysis -model "{model}" -config "{cfg}" -analysis-threads {config["threads"]}'
            )
        self.start()

    def start(self):
        with self.thread_lock:
            self.write_queue = queue.Queue()
            try:
                self.katrain.log(f"Starting KataGo with {self.command}", OUTPUT_DEBUG)
                startupinfo = None
                if hasattr(subprocess, "STARTUPINFO"):
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # stop command box popups on win/pyinstaller
                self.katago_process = subprocess.Popen(
                    self.command,
                    startupinfo=startupinfo,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=self.shell,
                )
            except (FileNotFoundError, PermissionError, OSError) as e:
                self.katrain.log(
                    i18n._("Starting Kata failed").format(command=self.command, error=e),
                    OUTPUT_ERROR,
                )
                return  # don't start
            self.analysis_thread = threading.Thread(target=self._analysis_read_thread, daemon=True)
            self.stderr_thread = threading.Thread(target=self._read_stderr_thread, daemon=True)
            self.write_stdin_thread = threading.Thread(target=self._write_stdin_thread, daemon=True)
            self.analysis_thread.start()
            self.stderr_thread.start()
            self.write_stdin_thread.start()

    def on_new_game(self):
        self.base_priority += 1
        if not self.is_idle():
            with self.thread_lock:
                for query_id in list(self.queries.keys()):
                    self.terminate_query(query_id)
                self.queries = {}
                self.write_queue = queue.Queue()

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
                if code != 1:  # deliberate exit, already showed message?
                    self.katrain.log(died_msg, OUTPUT_ERROR)
                self.katago_process = None
            else:
                died_msg = i18n._("Engine died unexpectedly").format(error=os_error)
            raise EngineDiedException(died_msg)
        return ok

    def wait_to_finish(self):
        while self.queries and self.katago_process and self.katago_process.poll() is None:
            time.sleep(0.1)

    def shutdown(self, finish=False):
        process = self.katago_process
        if finish and process:
            self.wait_to_finish()
        if process:
            self.katago_process = None
            process.terminate()
        for t in [self.stderr_thread, self.analysis_thread, self.write_stdin_thread]:
            if t:
                t.join()

    def is_idle(self):
        return not self.queries and self.write_queue.empty()

    def queries_remaining(self):
        return len(self.queries) + int(not self.write_queue.empty())

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
                elif "terminateId" in analysis:
                    self.katrain.log(f"{analysis} received from KataGo", OUTPUT_DEBUG)
                else:
                    partial_result = analysis.get("isDuringSearch", False)
                    if not partial_result:
                        del self.queries[query_id]
                    time_taken = time.time() - start_time
                    results_exist = not analysis.get("noResults", False)
                    self.katrain.log(
                        f"[{time_taken:.1f}][{query_id}][{'....' if partial_result else 'done'}] KataGo analysis received: {len(analysis.get('moveInfos',[]))} candidate moves, {analysis['rootInfo']['visits'] if results_exist else 'n/a'} visits",
                        OUTPUT_DEBUG,
                    )
                    self.katrain.log(json_truncate_arrays(analysis), OUTPUT_EXTRA_DEBUG)
                    try:
                        if callback and results_exist:
                            callback(analysis, partial_result)
                    except Exception as e:
                        self.katrain.log(f"Error in engine callback for query {query_id}: {e}", OUTPUT_ERROR)
                if getattr(self.katrain, "update_state", None):  # easier mocking etc
                    self.katrain.update_state()
            except Exception as e:
                self.katrain.log(f"Unexpected exception {e} while processing KataGo output {line}", OUTPUT_ERROR)
                traceback.print_exc()

    def _write_stdin_thread(self):  # flush only in a thread since it returns only when the other program reads
        while self.katago_process is not None:
            try:
                query, callback, error_callback, next_move = self.write_queue.get(block=True, timeout=0.1)
            except queue.Empty:
                continue
            with self.thread_lock:
                if "id" not in query:
                    self.query_counter += 1
                    query["id"] = f"QUERY:{str(self.query_counter)}"
                self.queries[query["id"]] = (callback, error_callback, time.time(), next_move)
                self.katrain.log(f"Sending query {query['id']}: {json.dumps(query)}", OUTPUT_DEBUG)
                try:
                    self.katago_process.stdin.write((json.dumps(query) + "\n").encode())
                    self.katago_process.stdin.flush()
                except OSError as e:
                    self.check_alive(os_error=str(e), exception_if_dead=False)

    def send_query(self, query, callback, error_callback, next_move=None):
        self.write_queue.put((query, callback, error_callback, next_move))

    def terminate_query(self, query_id):
        if query_id is not None:
            self.send_query({"action": "terminate", "terminateId": query_id}, None, None)

    def request_analysis(
        self,
        analysis_node: GameNode,
        callback: Callable,
        error_callback: Optional[Callable] = None,
        visits: int = None,
        analyze_fast: bool = False,
        time_limit=True,
        find_alternatives: bool = False,
        region_of_interest: Optional[List] = None,
        priority: int = 0,
        ownership: Optional[bool] = None,
        next_move: Optional[GameNode] = None,
        extra_settings: Optional[Dict] = None,
        report_every: Optional[float] = None,
    ):
        nodes = analysis_node.nodes_from_root
        moves = [m for node in nodes for m in node.moves]
        initial_stones = [m for node in nodes for m in node.placements]
        if next_move:
            moves.append(next_move)
        if ownership is None:
            ownership = self.config["_enable_ownership"] and not next_move
        if visits is None:
            visits = self.config["max_visits"]
            if analyze_fast and self.config.get("fast_visits"):
                visits = self.config["fast_visits"]

        size_x, size_y = analysis_node.board_size

        if find_alternatives:
            avoid = [
                {
                    "moves": list(analysis_node.analysis["moves"].keys()),
                    "player": analysis_node.next_player,
                    "untilDepth": 1,
                }
            ]
        elif region_of_interest:
            xmin, xmax, ymin, ymax = region_of_interest
            avoid = [
                {
                    "moves": [
                        Move((x, y)).gtp()
                        for x in range(0, size_x)
                        for y in range(0, size_y)
                        if x < xmin or x > xmax or y < ymin or y > ymax
                    ],
                    "player": player,
                    "untilDepth": 1,  # tried a large number here, or 2, but this seems more natural
                }
                for player in "BW"
            ]
        else:
            avoid = []

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
            "includeMovesOwnership": ownership and not next_move,
            "includePolicy": not next_move,
            "initialStones": [[m.player, m.gtp()] for m in initial_stones],
            "initialPlayer": analysis_node.initial_player,
            "moves": [[m.player, m.gtp()] for m in moves],
            "overrideSettings": {**settings, **(extra_settings or {})},
        }
        if report_every is not None:
            query["reportDuringSearchEvery"] = report_every
        if avoid:
            query["avoidMoves"] = avoid
        self.send_query(query, callback, error_callback, next_move)
        analysis_node.analysis_visits_requested = max(analysis_node.analysis_visits_requested, visits)
