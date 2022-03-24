import json
import os
import random
import shlex
import shutil
import signal
import subprocess
import threading
import time
import traceback
from collections import defaultdict

from katrain.core.constants import OUTPUT_DEBUG, OUTPUT_ERROR, OUTPUT_INFO, OUTPUT_KATAGO_STDERR, DATA_FOLDER
from katrain.core.engine import BaseEngine
from katrain.core.game import BaseGame
from katrain.core.lang import i18n
from katrain.core.sgf_parser import Move
from katrain.core.utils import find_package_resource


class KataGoContributeEngine(BaseEngine):
    """Starts and communicates with the KataGo contribute program"""

    DEFAULT_MAX_GAMES = 8

    SHOW_RESULT_TIME = 5
    GIVE_UP_AFTER = 120

    def __init__(self, katrain):
        super().__init__(katrain, katrain.config("contribute"))
        self.katrain = katrain
        base_dir = os.path.expanduser("~/.katrain/katago_contribute")
        self.katago_process = None
        self.stdout_thread = None
        self.stderr_thread = None
        self.shell = False
        self.active_games = {}
        self.finished_games = set()
        self.showing_game = None
        self.last_advance = 0
        self.move_count = 0
        self.uploaded_games_count = 0
        self.last_move_for_game = defaultdict(int)
        self.visits_count = 0
        self.start_time = 0
        self.server_error = None
        self.paused = False
        self.save_sgf = self.config.get("savesgf", False)
        self.save_path = self.config.get("savepath", "./dist_sgf/")
        self.move_speed = self.config.get("movespeed", 2.0)

        exe = self.get_engine_path(self.config.get("katago"))
        cacert_path = os.path.join(os.path.split(exe)[0], "cacert.pem")
        if not os.path.isfile(cacert_path):
            try:
                shutil.copyfile(find_package_resource("katrain/KataGo/cacert.pem"), cacert_path)
            except Exception as e:
                self.katrain.log(
                    f"Could not copy cacert file ({e}), please add it manually to your katago.exe directory",
                    OUTPUT_ERROR,
                )
        cfg = find_package_resource(self.config.get("config"))

        settings_dict = {
            "username": self.config.get("username"),
            "password": self.config.get("password"),
            "maxSimultaneousGames": self.config.get("maxgames") or self.DEFAULT_MAX_GAMES,
            "includeOwnership": self.config.get("ownership") or False,
            "logGamesAsJson": True,
            "homeDataDir": os.path.expanduser(DATA_FOLDER),
        }
        self.max_buffer_games = 2 * settings_dict["maxSimultaneousGames"]
        settings = {f"{k}={v}" for k, v in settings_dict.items()}
        self.command = shlex.split(
            f'"{exe}" contribute -config "{cfg}" -base-dir "{base_dir}" -override-config "{",".join(settings)}"'
        )
        self.start()

    @staticmethod
    def game_ended(game):
        cn = game.current_node
        if cn.is_pass and cn.analysis_exists:
            moves = cn.candidate_moves
            if moves and moves[0]["move"] == "pass":
                game.play(Move(None, player=game.current_node.next_player))  # play pass
        return game.end_result

    def advance_showing_game(self):
        current_game = self.active_games.get(self.showing_game)
        if current_game:
            end_result = self.game_ended(current_game)
            if end_result is not None:
                self.finished_games.add(self.showing_game)
                if time.time() - self.last_advance > self.SHOW_RESULT_TIME:
                    del self.active_games[self.showing_game]
                    if self.save_sgf:
                        filename = os.path.join(self.save_path, f"{self.showing_game}.sgf")
                        self.katrain.log(current_game.write_sgf(filename, self.katrain.config("trainer")), OUTPUT_INFO)

                    self.katrain.log(f"Game {self.showing_game} finished, finding a new one", OUTPUT_INFO)
                    self.showing_game = None
            elif time.time() - self.last_advance > self.move_speed or len(self.active_games) > self.max_buffer_games:
                if current_game.current_node.children:
                    current_game.redo(1)
                    self.last_advance = time.time()
                    self.katrain("update-state")
                elif time.time() - self.last_advance > self.GIVE_UP_AFTER:
                    self.katrain.log(
                        f"Giving up on game {self.showing_game} which appears stuck, finding a new one", OUTPUT_INFO
                    )
                    self.showing_game = None
        else:
            if self.active_games:
                self.showing_game = None
                best_count = -1
                for game_id, game in self.active_games.items():  # find game with most moves left to show
                    count = 0
                    node = game.current_node
                    while node.children:
                        node = node.children[0]
                        count += 1
                    if count > best_count:
                        best_count = count
                        self.showing_game = game_id
                self.last_advance = time.time()
                self.katrain.log(f"Showing game {self.showing_game}, {best_count} moves left to show.", OUTPUT_INFO)

                self.katrain.game = self.active_games[self.showing_game]
                self.katrain("update-state", redraw_board=True)

    def status(self):
        return f"Contributing to distributed training\nGames: {self.uploaded_games_count} uploaded, {len(self.active_games)} in buffer, {len(self.finished_games)} shown\n{self.move_count} moves played ({60*self.move_count/(time.time()-self.start_time):.1f}/min, {self.visits_count / (time.time() - self.start_time):.1f} visits/s)\n"

    def is_idle(self):
        return False

    def queries_remaining(self):
        return 1


    def start(self):
        try:
            self.katrain.log(f"Starting Distributed KataGo with {self.command}", OUTPUT_INFO)
            startupinfo = None
            if hasattr(subprocess, "STARTUPINFO"):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # stop command box popups on win/pyinstaller
            self.katago_process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                startupinfo=startupinfo,
                shell=self.shell,
            )
        except (FileNotFoundError, PermissionError, OSError) as e:
            self.katrain.log(
                i18n._("Starting Kata failed").format(command=self.command, error=e),
                OUTPUT_ERROR,
            )
            return  # don't start
        self.paused = False
        self.stdout_thread = threading.Thread(target=self._read_stdout_thread, daemon=True)
        self.stderr_thread = threading.Thread(target=self._read_stderr_thread, daemon=True)
        self.stdout_thread.start()
        self.stderr_thread.start()

    def check_alive(self, os_error="", maybe_open_help=False):
        ok = self.katago_process and self.katago_process.poll() is None
        if not ok:
            if self.katago_process:
                code = self.katago_process and self.katago_process.poll()
                if code == 3221225781:
                    died_msg = i18n._("Engine missing DLL")
                else:
                    os_error += f"status {code}"
                    died_msg = i18n._("Engine died unexpectedly").format(error=os_error)
                if code != 1 and not self.server_error:  # deliberate exit, already showed message?
                    self.katrain.log(died_msg, OUTPUT_ERROR)
                self.katago_process = None
        return ok

    def shutdown(self, finish=False):
        process = self.katago_process
        if process:
            self.katago_process.stdin.write(b"forcequit\n")
            self.katago_process.stdin.flush()
            self.katago_process = None
            process.terminate()
        if finish is not None:
            for t in [self.stderr_thread, self.stdout_thread]:
                if t:
                    t.join()

    def graceful_shutdown(self):
        """respond to esc"""
        if self.katago_process:
            self.katago_process.stdin.write(b"quit\n")
            self.katago_process.stdin.flush()
            self.katrain.log("Finishing games in progress and stopping contribution", OUTPUT_KATAGO_STDERR)

    def pause(self):
        """respond to pause"""
        if self.katago_process:
            if not self.paused:
                self.katago_process.stdin.write(b"pause\n")
                self.katago_process.stdin.flush()
                self.katrain.log("Pausing contribution", OUTPUT_KATAGO_STDERR)
            else:
                self.katago_process.stdin.write(b"resume\n")
                self.katago_process.stdin.flush()
                self.katrain.log("Resuming contribution", OUTPUT_KATAGO_STDERR)
            self.paused = not self.paused

    def _read_stderr_thread(self):
        while self.katago_process is not None:
            try:
                line = self.katago_process.stderr.readline()
                if line:
                    try:
                        message = line.decode(errors="ignore").strip()
                        if any(
                            s in message
                            for s in ["not status code 200 OK", "Server returned error", "Uncaught exception:"]
                        ):
                            message = message.replace("what():", "").replace("Uncaught exception:", "").strip()
                            self.server_error = message  # don't be surprised by engine dying
                            self.katrain.log(message, OUTPUT_ERROR)
                            return
                        else:
                            self.katrain.log(message, OUTPUT_KATAGO_STDERR)
                    except Exception as e:
                        print("ERROR in processing KataGo stderr:", line, "Exception", e)
                elif self.katago_process and not self.check_alive():
                    return
            except Exception as e:
                self.katrain.log(f"Exception in reading stdout {e}", OUTPUT_DEBUG)
                return

    def _read_stdout_thread(self):
        while self.katago_process is not None:
            try:
                line = self.katago_process.stdout.readline()
                if line:
                    line = line.decode(errors="ignore").strip()
                    if line.startswith("{"):
                        try:
                            analysis = json.loads(line)
                            if "gameId" in analysis:
                                game_id = analysis["gameId"]
                                if game_id in self.finished_games:
                                    continue
                                current_game = self.active_games.get(game_id)
                                new_game = current_game is None
                                if new_game:
                                    board_size = [analysis["boardXSize"], analysis["boardYSize"]]
                                    placements = {
                                        f"A{bw}": [
                                            Move.from_gtp(move, pl).sgf(board_size)
                                            for pl, move in analysis["initialStones"]
                                            if pl == bw
                                        ]
                                        for bw in "BW"
                                    }
                                    game_properties = {k: v for k, v in placements.items() if v}
                                    game_properties["SZ"] = f"{board_size[0]}:{board_size[1]}"
                                    game_properties["KM"] = analysis["rules"]["komi"]
                                    game_properties["RU"] = json.dumps(analysis["rules"])
                                    game_properties["PB"] = analysis["blackPlayer"]
                                    game_properties["PW"] = analysis["whitePlayer"]
                                    current_game = BaseGame(
                                        self.katrain, game_properties=game_properties, bypass_config=True
                                    )
                                    self.active_games[game_id] = current_game
                                last_node = current_game.sync_branch(
                                    [Move.from_gtp(coord, pl) for pl, coord in analysis["moves"]]
                                )
                                last_node.set_analysis(analysis)
                                if new_game:
                                    current_game.set_current_node(last_node)
                                self.start_time = self.start_time or time.time() - 1
                                self.move_count += 1
                                self.visits_count += analysis["rootInfo"]["visits"]
                                last_move = self.last_move_for_game[game_id]
                                self.last_move_for_game[game_id] = time.time()
                                dt = self.last_move_for_game[game_id] - last_move if last_move else 0
                                self.katrain.log(
                                    f"[{time.time()-self.start_time:.1f}] Game {game_id} Move {analysis['turnNumber']}: {' '.join(analysis['move'])} Visits {analysis['rootInfo']['visits']} Time {dt:.1f}s\t Moves/min {60*self.move_count/(time.time()-self.start_time):.1f} Visits/s {self.visits_count/(time.time()-self.start_time):.1f}",
                                    OUTPUT_DEBUG,
                                )
                                self.katrain("update-state")
                        except Exception as e:
                            traceback.print_exc()
                            self.katrain.log(f"Exception {e} in parsing or processing JSON: {line}", OUTPUT_ERROR)
                    elif "uploaded sgf" in line:
                        self.uploaded_games_count += 1
                    else:
                        self.katrain.log(line, OUTPUT_KATAGO_STDERR)
                elif self.katago_process and not self.check_alive():  # stderr will do this
                    return
            except Exception as e:
                self.katrain.log(f"Exception in reading stdout {e}", OUTPUT_DEBUG)
                return
