import copy
import json
import os
import platform
import queue
import shlex
import subprocess
import threading
import time
import traceback
from typing import Callable, Dict, List, Optional

from kivy.utils import platform as kivy_platform

from katrain.core.constants import (
    OUTPUT_DEBUG,
    OUTPUT_ERROR,
    OUTPUT_EXTRA_DEBUG,
    OUTPUT_KATAGO_STDERR,
    DATA_FOLDER,
    KATAGO_EXCEPTION,
    PONDERING_REPORT_DT,
)
from katrain.core.game_node import GameNode
from katrain.core.lang import i18n
from katrain.core.sgf_parser import Move
from katrain.core.utils import find_package_resource, json_truncate_arrays


class BaseEngine:  # some common elements between analysis and contribute engine

    RULESETS_ABBR = [
        ("jp", "japanese"),
        ("cn", "chinese"),
        ("ko", "korean"),
        ("aga", "aga"),
        ("tt", "tromp-taylor"),
        ("nz", "new zealand"),
        ("stone_scoring", "stone_scoring"),
    ]
    RULESETS = {fromkey: name for abbr, name in RULESETS_ABBR for fromkey in [abbr, name]}

    def __init__(self, katrain, config):
        self.katrain = katrain
        self.config = config

    @staticmethod
    def get_rules(ruleset):
        if ruleset.strip().startswith("{"):
            try:
                ruleset = json.loads(ruleset)
            except json.JSONDecodeError:
                pass
        if isinstance(ruleset, dict):
            return ruleset
        return KataGoEngine.RULESETS.get(str(ruleset).lower(), "japanese")

    def advance_showing_game(self):
        pass  # avoid transitional error

    def status(self):
        return ""  # avoid transitional error

    def get_engine_path(self, exe):
        if not exe:
            if kivy_platform == "win":
                exe = "katrain/KataGo/katago.exe"
            elif kivy_platform == "linux":
                exe = "katrain/KataGo/katago"
            else:
                exe = find_package_resource("katrain/KataGo/katago-osx")  # github actions built
                if not os.path.isfile(exe) or "arm64" in platform.version().lower():
                    exe = "katago"  # e.g. MacOS after brewing
        if exe.startswith("katrain"):
            exe = find_package_resource(exe)
        exepath, exename = os.path.split(exe)

        if exepath and not os.path.isfile(exe):
            self.on_error(i18n._("Kata exe not found").format(exe=exe), "KATAGO-EXE")
            return None
        elif not exepath:
            paths = os.getenv("PATH", ".").split(os.pathsep) + ["/opt/homebrew/bin/"]
            exe_with_paths = [os.path.join(path, exe) for path in paths if os.path.isfile(os.path.join(path, exe))]
            if not exe_with_paths:
                self.on_error(i18n._("Kata exe not found in path").format(exe=exe), "KATAGO-EXE")
                return None
            exe = exe_with_paths[0]
        return exe

    def on_error(self, message, code, allow_popup):
        print("ERROR", message, code)


class KataGoEngine(BaseEngine):
    """Starts and communicates with the KataGO analysis engine"""

    PONDER_KEY = "_kt_continuous"

    def __init__(self, katrain, config):
        super().__init__(katrain, config)

        self.allow_recovery = self.config.get("allow_recovery", True)  # if false, don't give popups
        self.queries = {}  # outstanding query id -> start time and callback
        self.ponder_query = None
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
        if config.get("altcommand", ""):
            self.command = config["altcommand"]
            self.shell = True
        else:
            model = find_package_resource(config["model"])
            cfg = find_package_resource(config["config"])
            exe = self.get_engine_path(config.get("katago", "").strip())
            if not exe:
                return
            if not os.path.isfile(model):
                self.on_error(i18n._("Kata model not found").format(model=model), code="KATAGO-FILES")
                return  # don't start
            if not os.path.isfile(cfg):
                self.on_error(i18n._("Kata config not found").format(config=cfg), code="KATAGO-FILES")
                return  # don't start
            self.command = shlex.split(
                f'"{exe}" analysis -model "{model}" -config "{cfg}" -analysis-threads {config["threads"]} -override-config "homeDataDir={os.path.expanduser(DATA_FOLDER)}"'
            )
        self.start()

    def on_error(self, message, code=None, allow_popup=True):
        self.katrain.log(message, OUTPUT_ERROR)
        if self.allow_recovery and allow_popup:
            self.katrain("engine_recovery_popup", message, code)

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
                self.on_error(i18n._("Starting Kata failed").format(command=self.command, error=e), code="c")
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
                self.write_queue = queue.Queue()
                self.terminate_queries(only_for_node=None, lock=False)
                self.ponder_query = None
                self.queries = {}

    def terminate_queries(self, only_for_node=None, lock=True):
        if lock:
            with self.thread_lock:
                return self.terminate_queries(only_for_node=only_for_node, lock=False)
        for query_id, (_, _, _, _, node) in list(self.queries.items()):
            if only_for_node is None or only_for_node is node:
                self.terminate_query(query_id)

    def stop_pondering(self):
        pq = self.ponder_query
        if pq:
            self.terminate_query(pq["id"], ignore_further_results=False)
        self.ponder_query = None

    def terminate_query(self, query_id, ignore_further_results=True):
        self.katrain.log(f"Terminating query {query_id}", OUTPUT_DEBUG)

        if query_id is not None:
            self.send_query({"action": "terminate", "terminateId": query_id}, None, None)
            if ignore_further_results:
                self.queries.pop(query_id, None)

    def restart(self):
        self.queries = {}
        self.shutdown(finish=False)
        self.start()

    def check_alive(self, os_error="", exception_if_dead=False, maybe_open_recovery=False):
        ok = self.katago_process and self.katago_process.poll() is None
        if not ok and exception_if_dead:
            if self.katago_process:
                code = self.katago_process and self.katago_process.poll()
                if code == 3221225781:
                    died_msg = i18n._("Engine missing DLL")
                else:
                    died_msg = i18n._("Engine died unexpectedly").format(error=f"{os_error} status {code}")
                if code != 1:  # deliberate exit
                    self.on_error(died_msg, code, allow_popup=maybe_open_recovery)
                self.katago_process = None  # return from threads
            else:
                self.katrain.log(i18n._("Engine died unexpectedly").format(error=os_error), OUTPUT_DEBUG)
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
            self.katrain.log("Terminating KataGo process", OUTPUT_DEBUG)
            process.terminate()
            self.katrain.log("Terminated KataGo process", OUTPUT_DEBUG)
        if finish is not None:  # don't care if exiting app
            for t in [self.write_stdin_thread, self.analysis_thread, self.stderr_thread]:
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
                    if b"Uncaught exception" in line or b"what()" in line:  # linux=what
                        msg = f"KataGo Engine Failed: {line.decode(errors='ignore')[9:].strip()}"
                        self.on_error(msg, KATAGO_EXCEPTION)
                        return
                    try:
                        self.katrain.log(line.decode(errors="ignore").strip(), OUTPUT_KATAGO_STDERR)
                    except Exception as e:
                        print("ERROR in processing KataGo stderr:", line, "Exception", e)
                elif not self.check_alive(exception_if_dead=True):
                    return
            except Exception as e:
                self.katrain.log(f"Exception in reading stderr: {e}", OUTPUT_DEBUG)
                return

    def _analysis_read_thread(self):
        while self.katago_process is not None:
            try:
                line = self.katago_process.stdout.readline().strip()
                if self.katago_process and not line:
                    if not self.check_alive(exception_if_dead=True, maybe_open_recovery=True):
                        return
            except OSError as e:
                self.check_alive(os_error=str(e), exception_if_dead=True, maybe_open_recovery=True)
                return

            if b"Uncaught exception" in line:
                msg = f"KataGo Engine Failed: {line.decode(errors='ignore')}"
                self.on_error(msg, KATAGO_EXCEPTION)
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
                    if analysis.get("action") != "terminate":
                        self.katrain.log(
                            f"Query result {query_id} discarded -- recent new game or node reset?", OUTPUT_DEBUG
                        )
                    continue
                callback, error_callback, start_time, next_move, _ = self.queries[query_id]
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
                        traceback.print_exc()
                if getattr(self.katrain, "update_state", None):  # easier mocking etc
                    self.katrain.update_state()
            except Exception as e:
                self.katrain.log(f"Unexpected exception {e} while processing KataGo output {line}", OUTPUT_ERROR)
                traceback.print_exc()

    def _write_stdin_thread(self):  # flush only in a thread since it returns only when the other program reads
        while self.katago_process is not None:
            try:
                query, callback, error_callback, next_move, node = self.write_queue.get(block=True, timeout=0.1)
            except queue.Empty:
                continue
            with self.thread_lock:
                if "id" not in query:
                    self.query_counter += 1
                    query["id"] = f"QUERY:{str(self.query_counter)}"

                ponder = query.pop(self.PONDER_KEY, False)
                if ponder:  # handle pondering in here to be in lock and such
                    pq = self.ponder_query or {}
                    # basically we handle pondering by just asking for these queries a lot and ignoring duplicates
                    # when a different ponder query comes in, e.g. due to selecting a roi or different node, switch
                    differences = {
                        k: (pq.get(k), query.get(k))
                        for k in (query.keys() | pq.keys()) - {"id", "maxVisits", "reportDuringSearchEvery"}
                        if pq.get(k) != query.get(k)
                    }
                    if differences:
                        # TODO:remove
                        self.katrain.log(f"Found differences in ponder check: {differences}", OUTPUT_EXTRA_DEBUG)
                        self.stop_pondering()
                        query["maxVisits"] = 1_000_000
                        query["reportDuringSearchEvery"] = PONDERING_REPORT_DT
                        self.ponder_query = query
                    else:
                        # TODO:remove
                        self.katrain.log("Found no differences in ponder check, skipping", OUTPUT_EXTRA_DEBUG)
                        continue

                terminate = query.get("action") == "terminate"
                if not terminate:
                    self.queries[query["id"]] = (callback, error_callback, time.time(), next_move, node)
                tag = "ponder " if ponder else ("terminate " if terminate else "")
                self.katrain.log(f"Sending {tag}query {query['id']}: {json.dumps(query)}", OUTPUT_DEBUG)
                try:
                    self.katago_process.stdin.write((json.dumps(query) + "\n").encode())
                    self.katago_process.stdin.flush()
                except OSError as e:
                    self.katrain.log(f"Exception in writing to katago: {e}", OUTPUT_DEBUG)
                    return  # some other thread will take care of this

    def send_query(self, query, callback, error_callback, next_move=None, node=None):
        self.write_queue.put((query, callback, error_callback, next_move, node))

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
        ponder=False,  # infinite visits, cancellable
        ownership: Optional[bool] = None,
        next_move: Optional[GameNode] = None,
        extra_settings: Optional[Dict] = None,
        report_every: Optional[float] = None,
    ):
        nodes = analysis_node.nodes_from_root
        moves = [m for node in nodes for m in node.moves]
        initial_stones = [m for node in nodes for m in node.placements]
        clear_placements = [m for node in nodes for m in node.clear_placements]
        if clear_placements:  # TODO: support these
            self.katrain.log(f"Not analyzing node {analysis_node} as there are AE commands in the path", OUTPUT_DEBUG)
            return

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
            "rules": self.get_rules(analysis_node.ruleset),
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
            self.PONDER_KEY: ponder,
        }
        if report_every is not None:
            query["reportDuringSearchEvery"] = report_every
        if avoid:
            query["avoidMoves"] = avoid
        self.send_query(query, callback, error_callback, next_move, analysis_node)
        analysis_node.analysis_visits_requested = max(analysis_node.analysis_visits_requested, visits)
