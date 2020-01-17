from kivy.storage.jsonstore import JsonStore
from kivy.uix.gridlayout import GridLayout

from engine import KataEngine
from move import Move

Config = JsonStore("config.json")


class EngineControls(GridLayout):
    def __init__(self, **kwargs):
        super(EngineControls, self).__init__(**kwargs)
        self.engine = KataEngine(self, Config)

    def restart(self, boardsize=None):
        self.engine.restart(boardsize)

    def action(self, message, *args):
        self.engine.action(message, *args)

    @property
    def ready(self):
        return self.engine.ready

    @property
    def boardsize(self):
        return self.engine.boardsize

    @property
    def stones(self):
        return self.engine.stones

    @property
    def moves(self):
        return self.engine.moves

    @property
    def current_player(self):
        return self.engine.current_player()

    def redraw(self, include_board=False):
        if include_board:
            self.parent.board.draw_board()
        self.parent.board.redraw()

    def update_analysis(self, analysis, mode, ownership):
        for d in analysis:
            d["scoreMean"] = float(d["scoreMean"])

        if mode == 0:
            pm = [d for d in analysis if d["move"] == "pass"]
            npm = [d for d in analysis if d["move"] != "pass"]
            if pm:
                pv = sum([int(d["visits"]) for d in pm], 0)
                npv = sum([int(d["visits"]) for d in npm], 0)
                print("pass visits", pv, "other", npv)
                if pv > npv:
                    print(analysis)
            self.moves[-1].pass_analysis = [d for d in analysis if d["move"] != "pass"]
        else:
            if ownership:
                self.moves[-1].ownership = [float(p) for p in ownership[0].strip().split(" ")]
            best = analysis[0]["scoreMean"]
            worst = -self.moves[-1].pass_analysis[0]["scoreMean"]
            for d in analysis:
                d["evaluation"] = (d["scoreMean"] - worst) / (best - worst)
            self.moves[-1].analysis = analysis

            if self.eval.active(1 - self.current_player):
                self.temperature.text = f"{self.moves[-1].temperature():.1f}"
                self.score.text = f"{Move.PLAYERS[self.current_player]}{float(analysis[0]['scoreMean']):+.1f}".replace("-", "\u2013")  # en dash
            if len(self.moves) >= 2 and self.moves[-2].analysis:
                self.moves[-1].evaluate(self.moves[-2])
                if self.eval.active(1 - self.current_player):
                    if self.moves[-1].evaluation:
                        self.evaluation.text = f"{100 * self.moves[-1].evaluation:.1f}%"
                    else:
                        self.evaluation.text = "N/A"
                self.redraw(include_board=False)  # for dots and stuff

    def sgf(self):
        def sgfify(mvs):
            return f"(;GM[1]FF[4]SZ[{self.boardsize}]KM[{self.engine.komi}]RU[CN];" + ";".join(mvs) + ")"

        def format_move(m, pm):
            undo_comment = "".join(f"\nUndo: {u.gtp()} was {100*u.evaluation:.1f}%" for u in pm.undos if u.evaluation)
            undo_cr = "".join(f"MA[{u.sgfcoords(self.boardsize)}]" for u in pm.undos if u.coords[0])
            if pm.analysis and pm.analysis[0]["move"] != "pass":
                best_sq = f"SQ[{Move(gtpcoords=pm.analysis[0]['move'], player=0).sgfcoords(self.boardsize)}]"
            else:
                best_sq = ""
            return m.sgf(self.boardsize) + f"C[{m.comment}{undo_comment}]{undo_cr}{best_sq}"

        sgfmoves_small = [mv.sgf(self.boardsize) for mv in self.moves[1:]]
        sgfmoves = [format_move(mv, pmv) for mv, pmv in zip(self.moves[1:], self.moves[:-1])]

        with open("out.sgf", "w") as f:
            f.write(sgfify(sgfmoves))
        return sgfify(sgfmoves_small)
