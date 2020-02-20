import copy
import json
import os
import math
import random
import re
import shlex
import subprocess
import sys
import threading
import time
from queue import Queue

from kivy.clock import Clock
from kivy.storage.jsonstore import JsonStore
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.checkbox import CheckBox
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from board import Board, IllegalMoveException, Move

config_file = sys.argv[1] if len(sys.argv) > 1 else "config.json"
print(f"Using config file {config_file}")
Config = JsonStore(config_file)


class EngineControls(GridLayout):
    def __init__(self, **kwargs):
        super(EngineControls, self).__init__(**kwargs)
        self.command = shlex.split(Config.get("engine")["command"])

        analysis_settings = Config.get("analysis")
        self.visits = [[analysis_settings["pass_visits"], analysis_settings["visits"]], [analysis_settings["pass_visits_fast"], analysis_settings["visits_fast"]]]
        self.train_settings = Config.get("trainer")
        self.debug = Config.get("debug")["level"]
        self.board_size = Config.get("board")["size"]
        self.ready = False
        self.message_queue = None
        self.board = Board(self.board_size)
        self.komi = 6.5  # loaded from config in init
        self.outstanding_analysis_queries = []  # allows faster interaction while kata is starting
        self.kata = None
        self.query_time = {}

    def redraw(self, include_board=False):
        if include_board:
            Clock.schedule_once(self.parent.board.draw_board, -1)  # main thread needs to do this
        Clock.schedule_once(self.parent.board.redraw, -1)

    def restart(self, board_size=None):
        self.ready = False
        if not self.message_queue:
            self.message_queue = Queue()
            self.engine_thread = threading.Thread(target=self._engine_thread, daemon=True).start()
        else:
            with self.message_queue.mutex:
                self.message_queue.queue.clear()
        self.action("init", board_size or self.board_size)

    def action(self, message, *args):
        self.message_queue.put([message, *args])

    # engine main loop
    def _engine_thread(self):
        try:
            self.kata = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        except FileNotFoundError:
            self.info.text = f"Starting kata with command '{self.command[0]}' failed. If you are on Mac or Linux, please edit configuration file '{config_file}' to point to the correct KataGo executable."
        self.analysis_thread = threading.Thread(target=self._analysis_read_thread, daemon=True).start()

        msg, *args = self.message_queue.get()
        while True:
            try:
                if self.debug:
                    print("MESSAGE", msg, args)
                getattr(self, f"_do_{msg.replace('-','_')}")(*args)
            except Exception as e:
                self.info.text = f"Exception in Engine thread: {e}"
                raise
            msg, *args = self.message_queue.get()

    def play(self, move, faster=False):
        try:
            mr = self.board.play(move)
        except IllegalMoveException as e:
            self.info.text = f"Illegal move: {str(e)}"
            return
        self.update_evaluation()
        if not mr.analysis_ready:  # replayed old move
            self._request_analysis(mr, faster=faster)
        return mr

    def show_evaluation_stats(self, move):
        if move.analysis_ready:
            self.score.text = move.format_score().replace("-", "\u2013")
            self.temperature.text = f"{move.temperature_stats[2]:.1f}"
            if move.parent and move.parent.analysis_ready:
                self.evaluation.text = f"{move.evaluation:.1%}"

    # handles showing completed analysis and triggered actions like auto undo and ai move
    def update_evaluation(self, undo_triggered=False):
        current_move = self.board.current_move
        self.score.set_prisoners(self.board.prisoner_count)
        if self.eval.active(current_move.player) and current_move is not self.board.root:
            self.info.text = current_move.comment(eval=self.eval.active(current_move.player), hints=self.hints.active(current_move.player))
        self.evaluation.text = ""
        if self.eval.active(current_move.player):
            self.show_evaluation_stats(current_move)

        if current_move.analysis_ready and current_move.parent and current_move.parent.analysis_ready and not current_move.children and not current_move.x_comment:
            # handle automatic undo
            if self.auto_undo.active(current_move.player) and not self.ai_auto.active(current_move.player) and not current_move.auto_undid:
                ts = self.train_settings
                # TODO: is this overly generous wrt low visit outdated evaluations?
                eval = max(current_move.evaluation, current_move.outdated_evaluation or 0)
                points_lost = (current_move.parent or current_move).temperature_stats[2] * (1 - eval)
                if eval < ts["undo_eval_threshold"] and points_lost >= ts["undo_point_threshold"]:
                    if self.num_undos(current_move) == 0:
                        current_move.x_comment = f"Move was below threshold, but no undo granted (probability is {ts['num_undo_prompts']:.0%}).\n"
                        self.update_evaluation()
                    else:
                        current_move.auto_undid = True
                        self.board.undo()
                        if len(current_move.parent.children) >= ts["num_undo_prompts"] + 1:
                            best_move = sorted([m for m in current_move.parent.children], key=lambda m: -(m.evaluation_info[0] or 0))[0]
                            best_move.x_comment = f"Automatically played as best option after max. {ts['num_undo_prompts']} undo(s).\n"
                            self.board.play(best_move)
                        self.update_evaluation()
                        return
            # ai player doesn't technically need parent ready, but don't want to override waiting for undo
            current_move = self.board.current_move  # this effectively checks undo didn't just happen
            if self.ai_auto.active(1 - current_move.player) and not self.board.game_ended:
                if current_move.children:
                    self.info.text = "AI paused since moves were undone. Press 'AI Move' or choose a move for the AI to continue playing."
                else:
                    self._do_aimove()
        self.redraw(include_board=False)

    # engine action functions
    def _do_play(self, *args):
        self.play(Move(player=self.board.current_player, coords=args[0]))

    def _do_aimove(self):
        ts = self.train_settings
        while not self.board.current_move.analysis_ready:
            self.info.text = "Thinking..."
            time.sleep(0.05)
        # select move
        current_move = self.board.current_move
        pos_moves = [(d["move"], float(d["scoreLead"]), d["evaluation"]) for d in current_move.ai_moves if int(d["visits"]) >= ts["balance_play_min_visits"]]
        sel_moves = pos_moves[:1]
        # don't play suicidal to balance score - pass when it's best
        if self.ai_balance.active and pos_moves[0][0] != "pass":
            sel_moves = [
                (move, score, eval)
                for move, score, eval in pos_moves
                if eval > ts["balance_play_randomize_eval"]
                and -current_move.player_sign * score > 0
                or eval > ts["balance_play_min_eval"]
                and -current_move.player_sign * score > ts["balance_play_target_score"]
            ] or sel_moves
        aimove = Move(player=self.board.current_player, gtpcoords=random.choice(sel_moves)[0], robot=True)
        if len(sel_moves) > 1:
            aimove.x_comment = "AI Balance on, moves considered: " + ", ".join(f"{move} ({aimove.format_score(score)})" for move, score, _ in sel_moves) + "\n"
        self.play(aimove)

    def num_undos(self, move):
        if self.train_settings["num_undo_prompts"] < 1:
            return int(move.undo_threshold < self.train_settings["num_undo_prompts"])
        else:
            return self.train_settings["num_undo_prompts"]

    def _do_undo(self):
        if (
            self.ai_lock.active
            and self.auto_undo.active(self.board.current_move.player)
            and len(self.board.current_move.parent.children) > self.num_undos(self.board.current_move)
            and not self.train_settings.get("dont_lock_undos")
        ):
            self.info.text = f"Can't undo this move more than {self.num_undos(self.board.current_move)} time(s) when locked"
            return
        self.board.undo()
        self.update_evaluation()

    def _do_redo(self):
        self.board.redo()
        self.update_evaluation()

    def _do_init(self, board_size, komi=None):
        self.board_size = board_size
        self.komi = float(komi or Config.get("board").get(f"komi_{board_size}", 6.5))
        self.board = Board(board_size)
        self._request_analysis(self.board.root)
        self.redraw(include_board=True)
        self.ready = True
        if self.ai_lock.active:
            self.ai_lock.checkbox._do_press()
        for el in [self.ai_lock.checkbox, self.hints.black, self.hints.white, self.ai_auto.black, self.ai_auto.white, self.auto_undo.black, self.auto_undo.white, self.ai_move]:
            el.disabled = False

    def _do_analyze_sgf(self, sgf, faster=False, rewind=False):
        sgfprops = {k: v for k, v in re.findall(r"\b(\w+)\[(.*?)\]", sgf)}
        size = int(sgfprops.get("SZ", self.board_size))
        sgfmoves = re.findall(r"\b([BW])\[([a-z]{2})\]", sgf)
        if not sgfmoves and not sgfprops:
            fileselect_popup = Popup(title="Double Click SGF file to analyze", size_hint=(0.8, 0.8))
            fc = FileChooserListView(multiselect=False, path=os.path.expanduser("~"), filters=["*.sgf"])
            blui = BoxLayout(orientation="horizontal", size_hint=(1, 0.1))
            cbfast = CheckBox(color=(0.95, 0.95, 0.95, 1))
            cbrewind = CheckBox(color=(0.95, 0.95, 0.95, 1))
            for widget in [Label(text="Analyze Extra Fast"), cbfast, Label(text="Rewind to start"), cbrewind]:
                blui.add_widget(widget)
            bl = BoxLayout(orientation="vertical")
            bl.add_widget(fc)
            bl.add_widget(blui)
            fileselect_popup.add_widget(bl)

            def readfile(files, mouse):
                fileselect_popup.dismiss()
                with open(files[0]) as f:
                    self.action("analyze-sgf", f.read(), cbfast.active, cbrewind.active)

            fc.on_submit = readfile
            fileselect_popup.open()
            return
        self._do_init(size, sgfprops.get("KM"))
        moves = [Move(player=Move.PLAYERS.index(p.upper()), sgfcoords=(mv, self.board_size)) for p, mv in sgfmoves]
        handicap = int(sgfprops.get("HA", 0))
        self.board.place_handicap_stones(handicap)  # not technically correct, should parse AB/AW
        if handicap > 0:
            self._request_analysis(self.board.current_move)
        for move in moves:
            self.play(move, faster=faster and move != moves[-1])
        if rewind:
            self.board.rewind()

    # analysis thread
    def _analysis_read_thread(self):
        while True:
            while self.outstanding_analysis_queries:
                self._send_analysis_query(self.outstanding_analysis_queries.pop(0))
            line = self.kata.stdout.readline()
            if not line:  # occasionally happens?
                return
            try:
                analysis = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"JSON decode error: '{e}' encountered after receiving input '{line}'")
                return
            if self.debug:
                print(f"[{time.time()-self.query_time.get(analysis['id'],0):.1f}] kata analysis received:", line[:80], "...")
            if "error" in analysis:
                print(analysis)
                self.info.text = f"ERROR IN KATA ANALYSIS: {analysis['error']}"
            else:
                self.board.store_analysis(analysis)
                self.update_evaluation()

    def _send_analysis_query(self, query):
        self.query_time[query["id"]] = time.time()
        if self.kata:
            self.kata.stdin.write((json.dumps(query) + "\n").encode())
            self.kata.stdin.flush()
        else:  # early on / root / etc
            self.outstanding_analysis_queries.append(copy.copy(query))

    def _request_analysis(self, move, faster=False):
        faster_fac = 5 if faster else 1
        move_id = move.id
        moves = self.board.moves
        fast = self.ai_fast.active
        query = {
            "id": str(move_id),
            "moves": [[m.bw_player(), m.gtp()] for m in moves],
            "rules": "japanese",
            "komi": self.komi,
            "boardXSize": self.board_size,
            "boardYSize": self.board_size,
            "analyzeTurns": [len(moves)],
            "includeOwnership": True,
            "maxVisits": self.visits[fast][1] // faster_fac,
        }
        if self.debug:
            print(f"sending query for move {move_id}: {str(query)[:80]}")
        self._send_analysis_query(query)
        query.update({"id": f"PASS_{move_id}", "maxVisits": self.visits[fast][0] // faster_fac, "includeOwnership": False})
        query["moves"] += [[move.bw_player(next_move=True), "pass"]]
        query["analyzeTurns"][0] += 1
        self._send_analysis_query(query)

    def output_sgf(self):
        return self.board.write_sgf(self.komi, self.train_settings)
