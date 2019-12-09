import random
import re
import shlex
import signal
import subprocess
import sys
import threading

DEBUG = True


class GoEngine:
    GTP_COORD = "ABCDEFGHJKLMNOPQRSTUVWYXYZ"
    SGF_COORD = [chr(i) for i in range(97, 123)]

    def __init__(self, boardsize=19):
        self.boardsize = boardsize
        self.moves = []
        self.stones = []  # TODO refactor stones vs moves distinction
        self.komi = 7.5
        self.turn = 0

    def start(self, boardsize):
        self.__init__(boardsize)

    def play(self, coords, player=None, temp=False):
        if not temp:
            self.moves.append((player or self.turn, *(coords or [None, None])))  # pass is x=y=None
            if not player:
                self.turn = 1 - self.turn

    def generate_move(self):
        for _ in range(1000):
            move = (random.randint(0, self.boardsize - 1), random.randint(0, self.boardsize - 1))
            if move not in [(x, y) for _, x, y in self.stones]:
                break
        self.play(move)

    def undo(self):
        if self.moves:
            self.moves.pop()
            self.turn = 1 - self.turn

    def gtp2ix(self, gtpmove):
        if "pass" in gtpmove:
            return (None, None)
        return (GoEngine.GTP_COORD.index(gtpmove[0]), int(gtpmove[1:]) - 1)

    def ix2gtp(self, coords):
        if not coords:
            return "pass"
        return GoEngine.GTP_COORD[coords[0]] + str(coords[1] + 1)

    def coord2sgf(self, pl, x, y):
        if x is None:
            return f"{'BW'[pl]}[]"
        else:
            return f"{'BW'[pl]}[{GoEngine.SGF_COORD[x]}{GoEngine.SGF_COORD[self.boardsize - y - 1]}]"

    def sgf(self):
        sgfmoves = [self.coord2sgf(pl, x, y) for pl, x, y in self.moves]
        return f"(;GM[1]SZ[{self.boardsize}]KM[{self.komi}];" + ";".join(sgfmoves) + ")"


NEXT_BEST_PLAYOUTS = 1000
PASS_PLAYOUTS = 250


class KataEngine(GoEngine):
    # CMD = "kg/cpp/katago gtp -model modelb6/model.txt.gz -config katagtp.cfg"
    CMD = "../lizzie/katago/katago.exe gtp -model ../lizzie/katanetwork.gz -config katagtp.cfg"

    def __init__(self, boardsize=19):
        super().__init__(boardsize)
        self.stones = []
        self.temperature = 0
        if getattr(self, "kata", None):
            self.stop()
        else:
            signal.signal(signal.SIGINT, lambda *args: self.stop() and sys.exit(0))
        self.lock = threading.Lock()
        threading.Thread(target=self.create_pipe, daemon=True).start()

    def create_pipe(self):
        with self.lock:  # prevent other commands until started
            self.kata = subprocess.Popen(shlex.split(KataEngine.CMD), stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            self._command(f"boardsize {self.boardsize}")
        self.calc_temperature()

    def stop(self):
        if self.kata:
            print("STOPPING KATA")
            self.kata.terminate()

    def start(self, boardsize):
        self.__init__(boardsize)

    def _read(self):
        lines = []
        while self.kata:
            lines.append(self.kata.stdout.readline().decode())
            if DEBUG:
                print("READ", lines[-1].rstrip())
            if lines[-1].strip() == "":
                break
        return lines[:-1]

    def _write(self, cmd):
        if DEBUG:
            print("WRITE", cmd)
        self.kata.stdin.write((cmd + "\n").encode("utf-8"))
        self.kata.stdin.flush()

    def _command(self, cmd):
        self._write(cmd)
        return self._read()

    def _eq_command(self, cmd):
        return [l for l in self._command(cmd) if "=" in l][0][1:].strip()

    def current_player(self):
        return "BW"[self.turn]

    def generate_move(self):
        with self.lock:  # lock to ensure temp is done / hacky eh
            coords = self.gtp2ix(self.best_analysis[0]["move"])
        return self.play(coords)

    def _play(self, coords, player=None):
        self._command(f"play {player or self.current_player()} {self.ix2gtp(coords)}")

    def play(self, coords, player=None):
        with self.lock:
            self._play(coords, player)
            super().play(coords, player)
        self.update_position()
        best_score = float(self.best_analysis[0]["scoreMean"])
        worst_score = -float(self.pass_analysis[0]["scoreMean"])
        self.calc_temperature()
        last_move_score = -float(self.best_analysis[0]["scoreMean"])
        print("BEST", best_score, "WORST", worst_score, "LAST MOVE", last_move_score)
        return (last_move_score - worst_score) / (best_score - worst_score)

    def undo(self):
        with self.lock:
            super().undo()
            self._command("undo")
        self.update_position()

    def showboard(self):
        with self.lock:
            output = self._command("showboard")
            return [re.sub("[^\.ox]", "", l.lower()) for l in output[2:]]

    def update_position(self):
        print("UPDATING POSITION")
        board = self.showboard()
        self.stones = []
        for y, line in enumerate(board[::-1]):
            for x, st in enumerate(line):
                if st != ".":
                    self.stones.append(("xo".index(st), x, y))

    def analyze(self, nvisits=100, interval=10):
        self._write(f"kata-analyze interval {interval} ownership true")
        stopped = False
        move_dicts = []
        while self.kata:
            line = self.kata.stdout.readline().decode()
            if stopped and line.strip() == "":
                self._read()  # stop cause previous line break and then =, another double line break
                break
            elif "info" not in line:
                continue
            line, ownership = line.split("ownership")
            moves = [re.sub("pv .*", "", str).split(" ") for str in line.split("info ")[1:]]
            move_dicts = [{move[i]: move[i + 1] for i in range(0, len(move) - 1, 2)} for move in moves]
            tot_visits = sum([int(d["visits"]) for d in move_dicts], 0)
            if not stopped and tot_visits > nvisits:
                stopped = True
                self._write("stop")
        print("analyzed", move_dicts)
        return move_dicts  # {d['move']: d for d in move_dict} #/by order?

    def calc_temperature(self):
        with self.lock:
            self.best_analysis = self.analyze(NEXT_BEST_PLAYOUTS)
            print("playing pass")
            self._play((0, 0))  # pass does some weird things with pass being optimal
            print("analyzing post pass")
            self.pass_analysis = self.analyze(PASS_PLAYOUTS)
            self._command("undo")
            #  score after best move - score after pass = temp, but score after pass is negated here bc opponent's perspective
            self.temperature = float(self.best_analysis[0]["scoreMean"]) + float(self.pass_analysis[0]["scoreMean"])
            return self.temperature


if __name__ == "__main__":

    # https://github.com/lightvector/KataGo/issues/25
    k = KataEngine()

    # print(k.genmove("b"))
    # print(k.showboard())
    # print(k.genmove("w"))
    # print(k.showboard())
    # print(k.genmove("w"))
    # print(k.showboard())
    print(k.play((3, 3)))
    print("TEMPERATURE:", k.temperature())
    print(k.play((15, 3)))
    print("TEMPERATURE:", k.temperature())
    print(k.showboard())

    print(k.analyze(1000))
    print(k.play((0, 0)))
    print("TEMPERATURE:", k.temperature())
    print(k.showboard())

    # k.stop()

    # k.play('b','pass')
    # md = k.analyze()
