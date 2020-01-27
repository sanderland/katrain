import copy
import json
import random
import re
import shlex
import subprocess
import sys
import threading
import time
from queue import Queue

from kivy.storage.jsonstore import JsonStore
from kivy.uix.gridlayout import GridLayout

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

    def redraw(self, include_board=False):
        if include_board:
            self.parent.board.draw_board()
        self.parent.board.redraw()

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
        self.kata = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
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

    def play(self, move):
        try:
            mr = self.board.play(move)
        except IllegalMoveException as e:
            self.info.text = f"Illegal move: {str(e)}"
            return
        if not mr.analysis_ready:  # replayed old move
            self._request_analysis(mr)
        return mr

    # handles showing completed analysis and triggered actions like auto undo and ai move
    def update_evaluation(self, undo_triggered=False):
        current_move = self.board.current_move
        self.score.set_prisoners(self.board.prisoner_count)
        if self.eval.active(current_move.player):
            self.info.text = current_move.comment(eval=self.eval.active(current_move.player), hints=self.hints.active(current_move.player))
        self.evaluation.text = ""
        if current_move.analysis_ready and self.eval.active(current_move.player):
            self.score.text = current_move.format_score().replace("-", "\u2013")
            self.temperature.text = f"{current_move.temperature_stats[2]:.1f}"
            if current_move.parent and current_move.parent.analysis_ready:
                self.evaluation.text = f"{100 * current_move.evaluation:.1f}%"

        if current_move.analysis_ready and current_move.parent and current_move.parent.analysis_ready and not current_move.children:
            # handle automatic undo

            if self.auto_undo.active(current_move.player) and not self.ai_auto.active(current_move.player) and not current_move.auto_undid:
                ts = self.train_settings
                # TODO: is this overly generous wrt low visit outdated evaluations?
                eval = max(current_move.evaluation, current_move.outdated_evaluation or 0)
                points_lost = (current_move.parent or current_move).temperature_stats[2] * (1 - eval)
                if eval < ts["undo_eval_threshold"] and points_lost >= ts["undo_point_threshold"]:
                    current_move.auto_undid = True
                    self.board.undo()
                    if len(current_move.parent.children) >= ts["num_undo_prompts"] + 1:
                        best_move = sorted([m for m in current_move.parent.children], key=lambda m: -(m.evaluation_info[0] or 0))[0]
                        best_move.x_comment = f"Automatically played as best option after max. {ts['num_undo_prompts']} undo(s).\n"
                        self.board.play(best_move)
                    self.update_evaluation()
            # ai player doesn't technically need parent ready, but don't want to override waiting for undo
            current_move = self.board.current_move  # this effectively checks undo didn't just happen
            if self.ai_auto.active(1 - current_move.player) and not self.board.game_ended and not current_move.children:
                self._do_aimove()

    # engine action functions
    def _do_play(self, *args):
        self.play(Move(player=self.board.current_player, coords=args[0]))
        self.redraw()

    def _do_aimove(self):
        ts = self.train_settings
        while not self.board.current_move.analysis_ready:
            self.info.text = "Thinking..."
            time.sleep(0.05)
        # select move
        current_move = self.board.current_move
        pos_moves = [(d["move"], float(d["scoreMean"]), d["evaluation"]) for d in current_move.ai_moves if int(d["visits"]) >= ts["balance_play_min_visits"]]
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

    def _do_undo(self):
        if (
            self.ai_lock.active
            and self.auto_undo.active(self.board.current_move.parent.player)
            and len(self.board.current_move.parent.player.children) > self.train_settings["num_undo_prompts"]
        ):
            self.info.text = f"Can't undo more than {self.train_settings['num_undo_prompts']} time(s) when locked"
            return
        self.board.undo()

    def _do_init(self, board_size):
        self.board_size = board_size
        self.komi = Config.get("board")[f"komi_{board_size}"]
        self.board = Board(board_size)
        self._request_analysis(self.board.root)
        self.redraw(include_board=True)
        self.ready = True

    def _do_analyze_sgf(self, sgf):
        self._do_init(self.board_size)
        sgfmoves = re.findall(r"([BW])\[([a-z]{2})\]", sgf)
        moves = [Move(player=Move.PLAYERS.index(p.upper()), sgfcoords=(mv, self.board_size)) for p, mv in sgfmoves]
        for move in moves:
            self.play(move)

    # analysis thread
    def _analysis_read_thread(self):
        while True:
            while self.outstanding_analysis_queries:
                self._send_analysis_query(self.outstanding_analysis_queries.pop(0))
            line = self.kata.stdout.readline()
            if self.debug:
                print("KATA ANALYSIS RECEIVED:", line[:50])
            self.board.store_analysis(json.loads(line))
            self.update_evaluation()
            self.redraw(include_board=False)

    def _send_analysis_query(self, query):
        if self.kata:
            self.kata.stdin.write((json.dumps(query) + "\n").encode())
            self.kata.stdin.flush()
        else:  # early on / root / etc
            self.outstanding_analysis_queries.append(copy.copy(query))

    def _request_analysis(self, move):
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
            "maxVisits": self.visits[fast][1],
        }
        if self.debug:
            print(f"query for {move_id}")
        self._send_analysis_query(query)
        query.update({"id": f"PASS_{move_id}", "maxVisits": self.visits[fast][0], "includeOwnership": False})
        query["moves"] += [[move.bw_player(next_move=True), "pass"]]
        query["analyzeTurns"][0] += 1
        self._send_analysis_query(query)

    def output_sgf(self):
        return self.board.write_sgf(self.komi, self.train_settings)
