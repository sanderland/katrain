from kivy.storage.jsonstore import JsonStore
from kivy.uix.gridlayout import GridLayout
import json
import copy
import random
import re
import shlex
import subprocess
import threading
import time
from queue import Queue

from board import Board, Move, IllegalMoveException

Config = JsonStore("Config.json")


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
        self.outstanding_analysis_queries = [] # allows faster interaction while kata is starting
        self.kata = None

    @property
    def current_player(self):
        return self.board.current_player

    @property
    def stones(self):
        return self.board.stones

    @property
    def moves(self):
        return self.board.moves

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
        print("PLAYED",move,self.board.stones)
        self._request_analysis(mr)

    # engine action functions
    def _do_play(self, *args):
        print("CURRENT PLAYER",self.current_player)
        move = Move(player=self.current_player, coords=args[0])
        self.play(move)

        self.undo.disabled = True  # undo while waiting for this does weird things
        undid = False
        self.info.text = ""
        if self.auto_undo.active(1 - self.current_player):
            undid = self._auto_undo(move)
        if self.ai_auto.active and not undid:
            self._do_aimove(move,True)
        self.undo.disabled = False
        self.redraw()

    def _evaluate_move(self, move, show=True):
        while not move.analysis:
            time.sleep(0.01)  # wait for analysis
        if self.board.current_move.evaluation and show:
            self.info.text = f"Your move {self.moves[-1].gtp()} was {100 * self.moves[-1].evaluation:.1f}% efficient and lost {self.moves[-1].points_lost:.1f} point(s).\n"

    def _auto_undo(self, move):
        ts = self.train_settings
        self.info.text = "Evaluating..."
        self._evaluate_move()
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
                        [m for m in self.board.current_move.parent.children if m.evaluation], key=lambda m: -m.evaluation
                    )
                    if evaled_moves and evaled_moves[0].coords != move.coords:
                        self.board.undo()
                        self.board.play(evaled_moves[0])
                    summary = "\n".join(f"{m.gtp()}: {100*m.evaluation:.1f}% effective" for m in evaled_moves)
                    self.info.text += (
                        f"\nYour moves:\n{summary}.\nLet's continue with {evaled_moves[0].gtp()}.\n"
                    )
        return False

    def _do_aimove(self, move, auto=False):
        ts = self.train_settings
        if not auto:
            self.info.text = "Thinking..."
        self._evaluate_move(auto and not self.auto_undo.active(1 - self.current_player))
        # select move
        pos_moves = [
            (d["move"], float(d["scoreMean"]), d["evaluation"])
            for d in move.analysis
            if int(d["visits"]) >= ts["balance_play_min_visits"]
        ]
        if ts["show_ai_options"]:
            self.info.text += "AI Options: " + " ".join(
                [f"{move}({100*eval:.0f}%,{score:.1f}pt)" for move, score, eval in pos_moves]
            )
        selmove = pos_moves[0][0]
        if (
            self.ai_balance.active and pos_moves[0][0] != "pass"
        ):  # don't play suicidal to balance score - pass when it's best
            selmoves = [
                move
                for move, score, eval in pos_moves
                if eval > ts["balance_play_randomize_eval"]
                or eval > ts["balance_play_min_eval"]
                and score > ts["balance_play_target_score"]
            ]
            selmove = random.choice(selmoves)  # some kind of when further ahead play worse?
        self.board.play(Move(player=self.current_player, gtpcoords=selmove, robot=True))

    def _do_undo(self):
        if self.ai_auto.active and self.board.current_move.robot:
            self.board.undo()
        if (
            self.ai_lock.active
            and self.auto_undo.active(self.board.current_move.parent.player)
            and len(self.board.current_move.parent.player.children) > self.train_settings["num_undo_prompts"]
        ):
            self.info.text = (
                f"Can't undo more than {self.train_settings['num_undo_prompts']} time(s) when locked"
            )
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
                print("processing outstanding query")
                self._send_analysis_query(self.outstanding_analysis_queries.pop(0))
            print('reading kata line')
            line = self.kata.stdout.readline()
            print("KATA LINE", line)
            self.board.store_analysis(json.loads(line))

    def _send_analysis_query(self,query):
        if self.kata:
            self.kata.stdin.write((json.dumps(query) + "\n").encode())
            self.kata.stdin.flush()
        else: # early on / root / etc
            self.outstanding_analysis_queries.append(copy.copy(query))

    def _request_analysis(self, move):
        move_id = move.id
        moves = self.board.moves
        fast = self.ai_fast.active
        query = {
            "id": str(move_id),
            "moves": [str(m) for m in moves],
            "rules": "japanese",
            "komi": self.komi,
            "boardXSize": self.board_size,
            "boardYSize": self.board_size,
            "analyzeTurns": [len(moves)],
            "includeOwnership": True,
            "maxVisits": self.visits[fast][1],
        }
        print('query',query)
        self._send_analysis_query(query)
        query.update({"id": f"PASS_{move_id}", "maxVisits": self.visits[fast][0], "includeOwnership": False})  # TODO: merge?
        query["moves"] += ["pass"]
        query["analyzeTurns"][0] += 1
        print("pass-query", query)
        self._send_analysis_query(query)



#    def update_analysis(self, analysis, mode, ownership):
#        for d in analysis:
#            d["scoreMean"] = float(d["scoreMean"])
#
#        if mode == 0:
#            pm = [d for d in analysis if d["move"] == "pass"]
#            npm = [d for d in analysis if d["move"] != "pass"]
#            if pm:
#                pv = sum([int(d["visits"]) for d in pm], 0)
#                npv = sum([int(d["visits"]) for d in npm], 0)
#                print("pass visits", pv, "other", npv)
#                if pv > npv:
#                    print(analysis)
#            self.moves[-1].pass_analysis = [d for d in analysis if d["move"] != "pass"]
#        else:
#            if ownership:
#                self.moves[-1].ownership = [float(p) for p in ownership[0].strip().split(" ")]
#            best = analysis[0]["scoreMean"]
#            worst = -self.moves[-1].pass_analysis[0]["scoreMean"]
#            for d in analysis:
#                d["evaluation"] = (d["scoreMean"] - worst) / (best - worst)
#            self.moves[-1].analysis = analysis
#            if self.eval.active(1 - self.current_player):
#                self.temperature.text = f"{self.moves[-1].temperature():.1f}"
#                self.score.text = f"{Move.PLAYERS[self.current_player]}{float(analysis[0]['scoreMean']):+.1f}".replace("-", "\u2013")  # en dash
#            if len(self.moves) >= 2 and self.moves[-2].analysis:
#                self.moves[-1].evaluate(self.moves[-2])
#                if self.eval.active(1 - self.current_player):
#                    if self.moves[-1].evaluation:
#                       self.evaluation.text = f"{100 * self.moves[-1].evaluation:.1f}%"
#                    else:
#                        self.evaluation.text = "N/A"
#                self.redraw(include_board=False)  # for dots and stuff



    def sgf(self):
        def sgfify(mvs):
            return f"(;GM[1]FF[4]SZ[{self.board_size}]KM[{self.komi}]RU[CN];" + ";".join(mvs) + ")"

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
