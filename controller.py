import copy
import json
import random
import re
import shlex
import subprocess
import threading
import time
from queue import Queue

from kivy.storage.jsonstore import JsonStore
from kivy.uix.gridlayout import GridLayout

from board import Board, IllegalMoveException, Move

Config = JsonStore("config.json")


class EngineControls(GridLayout):
    def __init__(self, **kwargs):
        super(EngineControls, self).__init__(**kwargs)
        self.command = shlex.split(Config.get("engine")["command"])

        analysis_settings = Config.get("analysis")
        self.visits = [
            [analysis_settings["pass_visits"], analysis_settings["visits"]],
            [analysis_settings["pass_visits_fast"], analysis_settings["visits_fast"]],
        ]
        self.min_nopass_visits = analysis_settings["nopass_visits"]
        self.train_settings = Config.get("trainer")
        self.debug = Config.get("debug")["level"]
        self.board_size = Config.get("board")["size"]
        self.komi = Config.get("board")["komi"]
        self.ready = False
        self.message_queue = None
        self.board = Board(self.board_size)
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
            self.thread = threading.Thread(target=self._engine_thread, daemon=True).start()
        else:
            with self.message_queue.mutex:
                self.message_queue.queue.clear()
        self.action("init", board_size or self.board_size)

    def action(self, message, *args):
        self.message_queue.put([message, *args])

    # engine main loop
    def _engine_thread(self):
        self.kata = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        threading.Thread(target=self._analysis_read_thread, daemon=True).start()

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
            print(str(e))
            self.info.text = f"Illegal move: {str(e)}"
            return
        print("PLAYED", move, self.board.stones)
        self._request_analysis(mr)
        return mr

    # engine action functions
    def _do_play(self, *args):
        print("CURRENT PLAYER", self.board.current_player)
        move = Move(player=self.board.current_player, coords=args[0])
        self.play(move)
        # mr.waiting_for_analysis
        self.redraw()

    def update_evaluation(self):
        current_move = self.board.current_move
        if self.eval.active(current_move.player):
            self.info.text = current_move.comment
        self.evaluation.text = ''
        if current_move.analysis_ready:
            self.score.text = current_move.format_score().replace("-", "\u2013")
            self.temperature.text = f"{current_move.temperature_stats[2]:.1f}"
            if current_move.parent and current_move.parent.analysis_ready:
                self.evaluation.text = f"{100 * current_move.evaluation:.1f}%"

        # when to trigger auto undo?
#      self.undo.disabled = True  # undo while waiting for this does weird things
#      undid = False
#       self.info.text = ""
#        if self.auto_undo.active(1 - self.board.current_player):
#            undid = self._auto_undo(move)
#        if self.ai_auto.active and not undid:
#            self._do_aimove(move, True)
#        self.undo.disabled = False

    def _auto_undo(self, move):
        ts = self.train_settings
        self.info.text = "Evaluating..."
        if (
            move.evaluation
            and move.evaluation < ts["undo_eval_threshold"]
            and move.points_lost >= ts["undo_point_threshold"]
            and ts["num_undo_prompts"] > 0
        ):
            if move.outdated_evaluation:
                outdated_points_lost = (1 - move.outdated_evaluation) * move.points_lost / (1 - move.evaluation)
            # so if the move was not that far off (>undo_outdated_eval_threshold) and according to last move's analysis it was fine, don't undo.
            if (
                move.outdated_evaluation
                and (
                    move.outdated_evaluation >= ts["undo_eval_threshold"]
                    or outdated_points_lost < ts["undo_point_threshold"]
                )
                and (
                    move.evaluation > ts["undo_outdated_eval_threshold"]
                    or outdated_points_lost < ts["undo_point_threshold"]
                )
            ):
                self.info.text += f"\nBut according to my previous evaluation it was {move.outdated_evaluation*100:.1f}% effective and lost {outdated_points_lost:.1f} point(s), so let's continue anyway.\n"
            else:
                if len(self.board.current_move.parent.children) <= ts["num_undo_prompts"]:
                    self.info.text += f"\nLet's try again.\n"
                    self.board.undo()
                    return True
                else:
                    evaled_moves = sorted(
                        [m for m in self.board.current_move.parent.children if m.evaluation],
                        key=lambda m: -m.evaluation,
                    )
                    if evaled_moves and evaled_moves[0].coords != move.coords:
                        self.board.undo()
                        self.board.play(evaled_moves[0])
                    summary = "\n".join(f"{m.gtp()}: {100*m.evaluation:.1f}% effective" for m in evaled_moves)
                    self.info.text += f"\nYour moves:\n{summary}.\nLet's continue with {evaled_moves[0].gtp()}.\n"
        return False

    def _do_aimove(self, auto=False):
        ts = self.train_settings
        while not self.board.current_move.analysis_ready:
            self.info.text = "Thinking..."
            time.sleep(0.05)

        # select move
        current_move = self.board.current_move
        pos_moves = [
            (d["move"], float(d["scoreMean"]), d["evaluation"])
            for d in current_move.ai_moves
            if int(d["visits"]) >= ts["balance_play_min_visits"]
        ]
        selmove = pos_moves[0][0]
        # don't play suicidal to balance score - pass when it's best
        if self.ai_balance.active and pos_moves[0][0] != "pass":
            selmoves = [
                move
                for move, score, eval in pos_moves
                if eval > ts["balance_play_randomize_eval"]
                or eval > ts["balance_play_min_eval"]
                and current_move.player_sign * score > ts["balance_play_target_score"]
            ]
            selmove = random.choice(selmoves)  # TODO: some kind of when further ahead play worse?
            print('SEL',selmoves)
        print('POS',pos_moves, 'MOVE', selmove)
        self.play(Move(player=self.board.current_player, gtpcoords=selmove, robot=True))

    def _do_undo(self):
        if self.ai_auto.active and self.board.current_move.robot:
            self.board.undo()
        if (
            self.ai_lock.active
            and self.auto_undo.active(self.board.current_move.parent.player)
            and len(self.board.current_move.parent.player.children) > self.train_settings["num_undo_prompts"]
        ):
            self.info.text = f"Can't undo more than {self.train_settings['num_undo_prompts']} time(s) when locked"
            return
        self.board.undo()

    def _do_init(self, board_size, komi=None):
        self.board_size = board_size
        self.board = Board(board_size)
        self._request_analysis(self.board.root)
        self.redraw(include_board=True)
        self.ready = True

    def _do_analyze_sgf(self, sgf):
        self._do_init(self.board_size, self.komi)
        sgfmoves = re.findall(r"([BW])\[([a-z]{2})\]", sgf)
        moves = [Move(player=Move.PLAYERS.index(p.upper()), sgfcoords=(mv, self.board_size)) for p, mv in sgfmoves]
        for move in moves:
            self.board.play(move)
        while not all(m.analysis for m in moves):
            time.sleep(0.01)
            self.info.text = f"{sum([1 if m.analysis else 0 for m in moves])}/{len(moves)} analyzed"

    # analysis thread
    def _analysis_read_thread(self):
        while True:
            while self.outstanding_analysis_queries:
                self._send_analysis_query(self.outstanding_analysis_queries.pop(0))
            line = self.kata.stdout.readline()
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
        print("query", query)
        self._send_analysis_query(query)
        query.update(
            {"id": f"PASS_{move_id}", "maxVisits": self.visits[fast][0], "includeOwnership": False}
        )  # TODO: merge?
        query["moves"] += [[move.bw_player(next_move=True), "pass"]]
        query["analyzeTurns"][0] += 1
        print("pass-query", query)
        self._send_analysis_query(query)


    def sgf(self):
        def sgfify(mvs):
            return f"(;GM[1]FF[4]SZ[{self.board_size}]KM[{self.komi}]RU[JP];" + ";".join(mvs) + ")"

        def format_move(m, pm):
            undo_comment = "".join(f"\nUndo: {u.gtp()} was {100*u.evaluation:.1f}%" for u in pm.undos if u.evaluation)
            undo_cr = "".join(f"MA[{u.sgfcoords(self.board_size)}]" for u in pm.undos if u.coords[0])
            if pm.analysis and pm.analysis[0]["move"] != "pass":
                best_sq = f"SQ[{Move(gtpcoords=pm.analysis[0]['move'], player=0).sgfcoords(self.board_size)}]"
            else:
                best_sq = ""
            return m.sgf(self.board_size) + f"C[{m.comment}{undo_comment}]{undo_cr}{best_sq}"

        sgfmoves_small = [mv.sgf(self.board_size) for mv in self.moves[1:]]
        sgfmoves = [format_move(mv, pmv) for mv, pmv in zip(self.moves[1:], self.moves[:-1])]

        with open("out.sgf", "w") as f:
            f.write(sgfify(sgfmoves))
        return sgfify(sgfmoves_small)
