import re
import random
import shlex
import subprocess
import threading
import time
from queue import Queue
from move import Move


class KataEngine:
    def __init__(self, controls, config):
        self.controls = controls
        self.command = shlex.split(config.get("engine")["command"])

        analysis_settings = config.get("analysis")
        self.visits = [[analysis_settings["pass_visits"], analysis_settings["visits"]], [analysis_settings["pass_visits_fast"], analysis_settings["visits_fast"]]]
        self.min_nopass_visits = analysis_settings["nopass_visits"]
        self.train_settings = config.get("trainer")
        self.debug = config.get("debug")["level"]
        self.boardsize = config.get("board")["size"]
        self.komi = config.get("board")["komi"]
        self.ready = False
        self.stones = []
        self.message_queue = None
        self.moves = [Move(player=1, coords=(None, None))]  # sentinel

        self.kata = None

    def current_player(self):
        return 1 - self.moves[-1].player

    def restart(self, boardsize):
        self.ready = False
        if not self.message_queue:
            self.message_queue = Queue()
            self.analysis_semaphore = threading.Semaphore(1)
            self.stop_analyzing = True
            self.thread = threading.Thread(target=self._engine_thread, daemon=True).start()
        else:
            with self.message_queue.mutex:
                self.message_queue.queue.clear()
        self.stones = []
        self.action("init", boardsize or self.boardsize)

    def action(self, message, *args):
        self.message_queue.put([message, *args])

    def gtpread(self):
        lines = []
        while self.kata:
            lines.append(self.kata.stdout.readline().decode())
            if lines[-1].strip() == "":
                break
        return lines[:-1]

    def gtpwrite(self, cmd):
        if self.debug:
            print("WRITE", cmd)
        try:
            self.kata.stdin.write((cmd + "\n").encode("utf-8"))
            self.kata.stdin.flush()
        except Exception:
            self.controls.info.text = "Engine died, please restart app"
            raise

    def gtpcommand(self, cmd):
        self.gtpwrite(cmd)
        return self.gtpread()

    def raw_gtpplaycommand(self, move):
        if move == "undo":
            output = self.gtpcommand("undo")
        else:
            output = self.gtpcommand(f"play {Move.PLAYERS[move.player]} {move.gtp()}")
        output = "".join(output)
        if self.debug and "?" in output:
            print(move, output)
        return "?" not in output

    def update_stones(self):
        board_output = self.gtpcommand("showboard")
        info = self.gtpread() # new kata
        board = [re.sub(r"[^\.ox]", "", l.lower()) for l in board_output[2:]]
        self.stones = []
        for y, line in enumerate(board[::-1]):
            for x, st in enumerate(line):
                if st != ".":
                    self.stones.append(("xo".index(st), x, y))
        self.controls.redraw(include_board=False)

    def gtpplaycommand(self, move):
        self.stop_analyzing = True
        self.analysis_semaphore.acquire()
        if self.raw_gtpplaycommand(move):  # update moves array if engine accepts move
            if move == "undo":
                self.moves[-2].undos.append(self.moves[-1])
                self.moves.pop()
            else:
                self.moves[-1].undos = [m for m in self.moves[-1].undos if m.coords != move.coords]
                self.moves.append(move)
        self.update_stones()
        # start analyzing new board position
        self.stop_analyzing = False
        self.analysis_semaphore.release()

    # engine main loop
    def _engine_thread(self):
        self.kata = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        print(self.command, self.kata)
        analysis_thread = threading.Thread(target=self._analyze_thread, args=(25,), daemon=True).start()
        self.stop_analyzing = False

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

    # engine action functions
    def _do_play(self, *args):
        self.gtpplaycommand(Move(player=self.current_player(), coords=args[0]))
        self.controls.undo.disabled = True  # undo while waiting for this does weird things
        undid = False
        self.controls.info.text = ""
        if self.controls.auto_undo.active(1 - self.current_player()):
            print("undo active", self.current_player(), self.controls.auto_undo.active(self.current_player()))
            undid = self._auto_undo()
        if self.controls.ai_auto.active and not undid:
            self._do_aimove(True)
        self.controls.undo.disabled = False

    def _evaluate_move(self, show=True):
        while not self.moves[-1].analysis:  # ensure analysis has started, otherwise race condition on multi ai move
            time.sleep(0.01)
        self.analysis_semaphore.acquire() and self.analysis_semaphore.release()  # wait for analysis to finish
        if self.moves[-1].evaluation and show:
            self.controls.info.text = f"Your move {self.moves[-1].gtp()} was {100 * self.moves[-1].evaluation:.1f}% efficient and lost {self.moves[-1].points_lost:.1f} point(s).\n"

    def _auto_undo(self):
        ts = self.train_settings
        self.controls.info.text = "Evaluating..."
        self._evaluate_move()
        if (
            self.moves[-1].evaluation
            and self.moves[-1].evaluation < ts["undo_eval_threshold"]
            and self.moves[-1].points_lost >= ts["undo_point_threshold"]
            and ts["num_undo_prompts"] > 0
        ):
            if self.moves[-1].outdated_evaluation:
                outdated_points_lost = (1 - self.moves[-1].outdated_evaluation) * self.moves[-1].points_lost / (1 - self.moves[-1].evaluation)
            # so if the move was not that far off (>undo_outdated_eval_threshold) and according to last move's analysis it was fine, don't undo.
            if (
                self.moves[-1].outdated_evaluation
                and (self.moves[-1].outdated_evaluation >= ts["undo_eval_threshold"] or outdated_points_lost < ts["undo_point_threshold"])
                and (self.moves[-1].evaluation > ts["undo_outdated_eval_threshold"] or outdated_points_lost < ts["undo_point_threshold"])
            ):
                self.controls.info.text += f"\nBut according to my previous evaluation it was {self.moves[-1].outdated_evaluation*100:.1f}% effective and lost {outdated_points_lost:.1f} point(s), so let's continue anyway.\n"
            else:
                if len(self.moves[-2].undos) < ts["num_undo_prompts"]:
                    self.controls.info.text += f"\nLet's try again.\n"
                    self.gtpplaycommand("undo")
                    return True
                else:
                    evaled_moves = sorted([m for m in self.moves[-2].undos + [self.moves[-1]] if m.evaluation], key=lambda m: -m.evaluation)
                    if evaled_moves and evaled_moves[0].coords != self.moves[-1].coords:
                        self.gtpplaycommand("undo")
                        self.gtpplaycommand(evaled_moves[0])
                    summary = "\n".join(f"{m.gtp()}: {100*m.evaluation:.1f}% effective" for m in evaled_moves)
                    self.controls.info.text += f"\nYour moves:\n{summary}.\nLet's continue with {evaled_moves[0].gtp()}.\n"
        return False

    def _do_aimove(self, auto=False):
        ts = self.train_settings
        if not auto:
            self.controls.info.text = "Thinking..."
        self._evaluate_move(auto and not self.controls.auto_undo.active(1 - self.current_player()))
        # select move
        pos_moves = [(d["move"], float(d["scoreMean"]), d["evaluation"]) for d in self.moves[-1].analysis if int(d["visits"]) >= ts["balance_play_min_visits"]]
        if ts["show_ai_options"]:
            self.controls.info.text += "AI Options: " + " ".join([f"{move}({100*eval:.0f}%,{score:.1f}pt)" for move, score, eval in pos_moves])
        selmove = pos_moves[0][0]
        if self.controls.ai_balance.active and pos_moves[0][0] != "pass":  # don't play suicidal to balance score - pass when it's best
            selmoves = [
                move
                for move, score, eval in pos_moves
                if eval > ts["balance_play_randomize_eval"] or eval > ts["balance_play_min_eval"] and score > ts["balance_play_target_score"]
            ]
            selmove = random.choice(selmoves)  # some kind of when further ahead play worse?
        self.gtpplaycommand(Move(player=self.current_player(), gtpcoords=selmove, robot=True))

    def _do_undo(self):
        if self.controls.ai_auto.active and self.moves[-1].robot:
            self.gtpplaycommand("undo")
        if self.controls.ai_lock.active and self.controls.auto_undo.active(self.moves[-2].player) and len(self.moves[-2].undos) >= self.train_settings["num_undo_prompts"]:
            self.controls.info.text = f"Can't undo more than {self.train_settings['num_undo_prompts']} time(s) when locked"
            return
        self.gtpplaycommand("undo")

    def _do_init(self, boardsize, komi=None):
        self.boardsize = boardsize
        self.stop_analyzing = True
        self.analysis_semaphore.acquire()
        self.stones = []
        self.moves = [Move(player=1, coords=(None, None))]  # sentinel
        self.controls.redraw(include_board=True)
        self.gtpcommand(f"boardsize {boardsize}")
        self.gtpcommand(f"komi {komi or self.komi}")
        self.gtpcommand("clear_board")
        self.ready = True
        self.analysis_semaphore.release()
        self.stop_analyzing = False

    def _do_analyze_sgf(self, sgf):
        self._do_init(self.boardsize, self.komi)
        sgfmoves = re.findall(r"([BW])\[([a-z]{2})\]", sgf)
        for move in [Move(player=Move.PLAYERS.index(p.upper()), sgfcoords=(mv, self.boardsize)) for p, mv in sgfmoves]:
            while not self.moves[-1].analysis:
                time.sleep(0.01)
            self.analysis_semaphore.acquire() and self.analysis_semaphore.release()  # wait for analysis to finish
            self.gtpplaycommand(move)
            self.controls.info.text = f"Analyzing move {move.gtp()}"
        self.controls.info.text = "Analysis done!"

    # analysis thread
    def _analyze_thread(self, interval):
        while True:
            num_visits = self.visits[1 if self.controls.ai_fast.active else 0]
            while self.stop_analyzing:  # TODO: cleaner concurrency?
                time.sleep(0.01)
            self.analysis_semaphore.acquire()
            for mode in [0, 1]:  # pass, analyze
                if self.stop_analyzing:
                    break
                if mode == 0:
                    passmove = Move(player=self.current_player(), gtpcoords="pass")
                    if len(self.moves) >= 2:
                        undo_mode = 0  # reverse order mode
                        self.raw_gtpplaycommand("undo")
                        self.raw_gtpplaycommand("undo")
                        self.raw_gtpplaycommand(passmove)
                        if not self.raw_gtpplaycommand(self.moves[-1]):  # could not change order -> restore state and fall back
                            undo_mode = 1
                            self.raw_gtpplaycommand("undo")  # pass
                            self.raw_gtpplaycommand(self.moves[-2])
                            self.raw_gtpplaycommand(self.moves[-1])
                        elif not self.raw_gtpplaycommand(self.moves[-2]):  # could not change order -> restore state and fall back
                            undo_mode = 1
                            self.raw_gtpplaycommand("undo")  # moves[-1]
                            self.raw_gtpplaycommand("undo")  # pass
                            self.raw_gtpplaycommand(self.moves[-2])
                            self.raw_gtpplaycommand(self.moves[-1])
                    else:
                        undo_mode = 1 # play corner for pass mode
                    if undo_mode == 1:
                        for coords in [(0, 0), (0, self.boardsize - 1), (self.boardsize - 1, 0), (self.boardsize - 1, self.boardsize - 1), (None, None)]:
                            if self.raw_gtpplaycommand(Move(player=self.current_player(), coords=coords)):
                                break
                self.gtpwrite(f"kata-analyze interval {interval} minmoves 2 {'ownership true' if mode==1 else ''}")
                self.kata.stdout.readline()  # =
                tot_visits = tot_nopass_visits = 0
                while not self.stop_analyzing and (tot_visits < num_visits[mode] or tot_nopass_visits < self.min_nopass_visits):
                    line = self.kata.stdout.readline().decode()
                    line, *ownership = line.split("ownership")
                    moves = [re.sub("pv .*", "", str).split(" ") for str in line.split("info ")[1:]]
                    move_dicts = [{move[i]: move[i + 1] for i in range(0, len(move) - 1, 2)} for move in moves]
                    self.controls.update_analysis(move_dicts, mode, ownership)
                    tot_visits = sum([int(d["visits"]) for d in move_dicts], 0)
                    tot_nopass_visits = sum([int(d["visits"]) for d in move_dicts if d["move"] != "pass"], 0)
                    if self.debug:
                        print("mode=", mode, "visits=", tot_visits, "nopass=", tot_nopass_visits)  # , "stop_analyzing?", stop_analyzing
                self.gtpcommand("stop")  # reads for analyze empty line
                self.gtpread()  # for stop line empty line
                # for modes loop
                if mode == 0:  # undo A1
                    self.raw_gtpplaycommand("undo")
                    if undo_mode == 0:
                        self.raw_gtpplaycommand("undo")
                        self.raw_gtpplaycommand("undo")
                        self.raw_gtpplaycommand(self.moves[-2])
                        self.raw_gtpplaycommand(self.moves[-1])
                else:
                    self.stop_analyzing = True  # ehh
            self.analysis_semaphore.release()  # signal other threads waiting for analysis to finish
