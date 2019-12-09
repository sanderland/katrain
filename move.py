from kivy.storage.jsonstore import JsonStore


class Move:
    GTP_COORD = "ABCDEFGHJKLMNOPQRSTUVWYXYZ"
    PLAYERS = "BW"
    SGF_COORD = [chr(i) for i in range(97, 123)]

    def __init__(self, player, coords=None, gtpcoords=None, sgfcoords=None, robot=False):
        self.player = player
        self.robot = robot
        self.coords = coords or (gtpcoords and self.gtp2ix(gtpcoords)) or self.sgf2ix(sgfcoords)
        self.analysis = None
        self.outdated_evaluation = None
        self.pass_analysis = None
        self.evaluation = None
        self.ownership = None
        self.points_lost = 0
        self.previous_temperature = None
        self.undos = []
        self.comment = ""

    def __repr__(self):
        return f"{Move.PLAYERS[self.player]}{self.gtp()}"

    def temperature(self):
        if self.analysis:
            best_score = float(self.analysis[0]["scoreMean"])
            worst_score = -float(self.pass_analysis[0]["scoreMean"])
            return best_score - worst_score
        else:
            return 0

    def evaluate(self, previous_move):
        best_score = float(previous_move.analysis[0]["scoreMean"])
        worst_score = -float(previous_move.pass_analysis[0]["scoreMean"])
        last_move_score = -float(self.analysis[0]["scoreMean"])
        self.previous_temperature = best_score - worst_score
        self.points_lost = best_score - last_move_score
        prev_analysis_current_move = [d for d in previous_move.analysis if d["move"] == self.gtp()]

        if abs(self.previous_temperature) > 0.5:
            self.evaluation = (last_move_score - worst_score) / (best_score - worst_score)
            self.move_options = [previous_move.analysis[0]["scoreMean"]]
        else:
            self.evaluation = None
        if self.evaluation:
            self.comment = f"Evaluation: {100*self.evaluation:.1f}%{' (AI Move)' if self.robot else ''}\n"
            if prev_analysis_current_move:
                self.outdated_evaluation = (prev_analysis_current_move[0]["scoreMean"] - worst_score) / (best_score - worst_score)
                self.comment += f"(Was considered last move as: {100 * self.outdated_evaluation:.1f}%)\n"
        else:
            self.comment = "Temperature too low for evaluation\n"
        self.comment += f"Estimate point loss: {self.points_lost:.1f}\n"
        self.comment += f"Last move score was {last_move_score:.1f}\n"
        self.comment += f"Score of top move was {previous_move.analysis[0]['scoreMean']:.1f} @ {previous_move.analysis[0]['move']}\n"
        self.comment += f"Pass score was {worst_score:.1f}\n"

    def gtp2ix(self, gtpmove):
        if "pass" in gtpmove:
            return (None, None)
        return Move.GTP_COORD.index(gtpmove[0]), int(gtpmove[1:]) - 1

    def sgf2ix(self, sgfmove_with_boardsize):
        sgfmove, boardsize = sgfmove_with_boardsize
        if sgfmove == "":
            return (None, None)
        return Move.SGF_COORD.index(sgfmove[0]), boardsize - Move.SGF_COORD.index(sgfmove[1]) - 1

    def gtp(self):
        if self.coords[0] is None:
            return "pass"
        return Move.GTP_COORD[self.coords[0]] + str(self.coords[1] + 1)

    def sgfcoords(self, boardsize):
        return f"{Move.SGF_COORD[self.coords[0]]}{Move.SGF_COORD[boardsize - self.coords[1] - 1]}"

    def sgf(self, boardsize):
        if self.coords[0] is None:
            return f"{Move.PLAYERS[self.player]}[]"
        else:
            return f"{Move.PLAYERS[self.player]}[{self.sgfcoords(boardsize)}]"
