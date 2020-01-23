import json
import random
import re
import shlex
import subprocess
import threading
import time
from queue import Queue

from board import Board, IllegalMoveException
from move import Move


class KataEngine:
    def __init__(self, controls, config):
        self.controls = controls
        self.command = shlex.split(config.get("engine")["command"])

        analysis_settings = config.get("analysis")
        self.visits = [
            [analysis_settings["pass_visits"], analysis_settings["visits"]],
            [analysis_settings["pass_visits_fast"], analysis_settings["visits_fast"]],
        ]
        self.min_nopass_visits = analysis_settings["nopass_visits"]
        self.train_settings = config.get("trainer")
        self.debug = config.get("debug")["level"]
        self.boardsize = config.get("board")["size"]
        self.komi = config.get("board")["komi"]
        self.ready = False
        self.stones = []
        self.message_queue = None
        self.board = Board(self.boardsize)

        self.kata = None

    @property
    def current_player(self):
        return self.board.current_player

    def restart(self, boardsize):
        self.ready = False
        if not self.message_queue:
            self.message_queue = Queue()
            self.thread = threading.Thread(target=self._engine_thread, daemon=True).start()
        else:
            with self.message_queue.mutex:
                self.message_queue.queue.clear()
        self.stones = []
        self.action("init", boardsize or self.boardsize)

    def action(self, message, *args):
        self.message_queue.put([message, *args])

    # engine main loop
    def _engine_thread(self):
        self.kata = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        print("STARTING KATAGO", self.command, self.kata)
        analysis_thread = threading.Thread(target=self._analyze_thread, daemon=True).start()

        msg, *args = self.message_queue.get()
        while True:
            try:
                if self.debug:
                    print("MESSAGE", msg, args)
                getattr(self, f"_do_{msg.replace('-','_')}")(*args)
            except Exception as e:
                self.controls.info.text = f"Exception in Engine thread: {e}"
                raise
            msg, *args = self.message_queue.get()

    def play(self, move):
        try:
            mr = self.board.play(move)
        except IllegalMoveException as e:
            print(str(e))
            self.controls.info.text = f"Illegal move: {str(e)}"
            return
        print("PLAYED",move,self.board.stones)
        self._request_analysis(mr)

    def _request_analysis(self, move):
        while not self.kata:
            print("waiting for kata to start")
            time.sleep(0.05)
        move_id = move.id
        moves = self.board.moves
        fast = self.controls.ai_fast.active
        query = {
            "id": str(move_id),
            "moves": [str(m) for m in moves],
            "rules": "japanese",
            "komi": self.komi,
            "boardXSize": self.boardsize,
            "boardYSize": self.boardsize,
            "analyzeTurns": [len(moves) - 1],
            "includeOwnership": True,
            "maxVisits": self.visits[fast][1],
        }
        print("query", query)
        self.kata.stdin.write(json.dumps(query).encode())
        query.update({"id": f"PASS_{move_id}", "maxVisits": self.visits[fast][0], "includeOwnership": True})
        query["moves"] += ["pass"]
        query["analyzeTurns"][0] += 1

        print("pass-query", query)
        self.kata.stdin.write(json.dumps(query).encode())

    # engine action functions
    def _do_play(self, *args):
        move = Move(player=self.current_player, coords=args[0])
        self.play(move)

        self.controls.undo.disabled = True  # undo while waiting for this does weird things
        undid = False
        self.controls.info.text = ""
        if self.controls.auto_undo.active(1 - self.current_player):
            undid = self._auto_undo(move)
        if self.controls.ai_auto.active and not undid:
            self._do_aimove(move,True)
        self.controls.undo.disabled = False
        self.controls.redraw()

    def _evaluate_move(self, move, show=True):
        while not move.analysis:
            time.sleep(0.01)  # wait for analysis
        if self.board.current_move.evaluation and show:
            self.controls.info.text = f"Your move {self.moves[-1].gtp()} was {100 * self.moves[-1].evaluation:.1f}% efficient and lost {self.moves[-1].points_lost:.1f} point(s).\n"

    def _auto_undo(self, move):
        ts = self.train_settings
        self.controls.info.text = "Evaluating..."
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
                self.controls.info.text += f"\nBut according to my previous evaluation it was {move.outdated_evaluation*100:.1f}% effective and lost {outdated_points_lost:.1f} point(s), so let's continue anyway.\n"
            else:
                if len(self.board.current_move.parent.children) <= ts["num_undo_prompts"]:
                    self.controls.info.text += f"\nLet's try again.\n"
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
                    self.controls.info.text += (
                        f"\nYour moves:\n{summary}.\nLet's continue with {evaled_moves[0].gtp()}.\n"
                    )
        return False

    def _do_aimove(self, move, auto=False):
        ts = self.train_settings
        if not auto:
            self.controls.info.text = "Thinking..."
        self._evaluate_move(auto and not self.controls.auto_undo.active(1 - self.current_player))
        # select move
        pos_moves = [
            (d["move"], float(d["scoreMean"]), d["evaluation"])
            for d in move.analysis
            if int(d["visits"]) >= ts["balance_play_min_visits"]
        ]
        if ts["show_ai_options"]:
            self.controls.info.text += "AI Options: " + " ".join(
                [f"{move}({100*eval:.0f}%,{score:.1f}pt)" for move, score, eval in pos_moves]
            )
        selmove = pos_moves[0][0]
        if (
            self.controls.ai_balance.active and pos_moves[0][0] != "pass"
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
        if self.controls.ai_auto.active and self.board.current_move.robot:
            self.board.undo()
        if (
            self.controls.ai_lock.active
            and self.controls.auto_undo.active(self.board.current_move.parent.player)
            and len(self.board.current_move.parent.player.children) > self.train_settings["num_undo_prompts"]
        ):
            self.controls.info.text = (
                f"Can't undo more than {self.train_settings['num_undo_prompts']} time(s) when locked"
            )
            return
        self.board.undo()

    def _do_init(self, boardsize, komi=None):
        self.boardsize = boardsize
        self.stones = []
        self.board = Board(boardsize)
        self._request_analysis(self.board.root)
        self.controls.redraw(include_board=True)
        self.ready = True

    def _do_analyze_sgf(self, sgf):
        self._do_init(self.boardsize, self.komi)
        sgfmoves = re.findall(r"([BW])\[([a-z]{2})\]", sgf)
        moves = [Move(player=Move.PLAYERS.index(p.upper()), sgfcoords=(mv, self.boardsize)) for p, mv in sgfmoves]
        for move in moves:
            self.board.play(move)
        while not all(m.analysis for m in moves):
            time.sleep(0.01)
            self.controls.info.text = f"{sum([1 if m.analysis else 0 for m in moves])}/{len(moves)} analyzed"

    # analysis thread
    def _analyze_thread(self):
        while True:
            line = self.kata.stdout.readline()
            print("KATA LINE", line)
            self.board.store_analysis(json.loads(line))
