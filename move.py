from kivy.storage.jsonstore import JsonStore


class MoveTree:
    _move_id_counter = 0 # used to make a map to all moves across all games

    def __init__(self, board_size):
        self.root = Move(None, (None, None))
        self.current = self.root
        self.board_size = board_size
        self.all_moves = {}

    def play(self, move):
        move = self.current.play(move)
        if not move.id:
            move.id = MoveTree._move_id_counter
            MoveTree._move_id_counter += 1
        self.all_moves[move.id] = move

    def undo(self):
        if self.current != self.root:
            self.current = self.current.parent

    def store_analysis(self,json):
        id = int(json["id"])
        move = self.all_moves.get(id)
        if move: # else this should be old
            move.set
        else:
            print("WARNING: ORPHANED ANALYSIS FOUND - RECENT NEW GAME?")

    def moves(self):  # flat list of moves to current
        moves = []
        p = self.current
        while p != self.root:
            moves.append(p)
            p = p.parent
        return moves[::-1]

    def __iter__(self):
        return self.moves.__iter__()

    def __getitem__(self, ix):
        if ix == -1:
            return self.current
        else:
            return self.moves[ix]

    def sgf(self):
        return "SGF[]"


class Move:
    GTP_COORD = "ABCDEFGHJKLMNOPQRSTUVWYXYZ"
    PLAYERS = "BW"
    SGF_COORD = [chr(i) for i in range(97, 123)]

    def __init__(self, player, coords=None, gtpcoords=None, sgfcoords=None, robot=False):
        self.id = None
        self.player = player
        self.coords = coords or (gtpcoords and self.gtp2ix(gtpcoords)) or self.sgf2ix(sgfcoords)
        self.children = []
        self.parent = None
        self.robot = robot
        self.analysis = None
        self.outdated_evaluation = None
        self.pass_analysis = None
        self.evaluation = None
        self.ownership = None
        self.points_lost = 0
        self.previous_temperature = None
        self.comment = ""

    def __repr__(self):
        return f"{Move.PLAYERS[self.player]}{self.gtp()}"

    def __eq__(self, other):
        return self.coords == other.coords and self.player == other.player

    def play(self, move: MoveTree):
        try:
            return self.children[self.children.index(move)]
        except ValueError:
            move.parent = self
            self.children.append(move)
            return move

    def temperature(self):
        if self.analysis:
            best_score = float(self.analysis[0]["scoreMean"])
            worst_score = -float(self.pass_analysis[0]["scoreMean"])
            return best_score - worst_score
        else:
            return 0

    def evaluate(self,analysis):
        self.analysis = analysis
        previous_move = self.parent
        # TODO: update children?
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
                self.outdated_evaluation = (prev_analysis_current_move[0]["scoreMean"] - worst_score) / (
                    best_score - worst_score
                )
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
