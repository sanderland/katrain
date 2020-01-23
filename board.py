
class IllegalMoveException(Exception):
    pass

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
        self.pass_analysis = None
        self.outdated_evaluation = None
        self.evaluation = None
        self.ownership = None
        self.points_lost = 0
        self.previous_temperature = None
        self.comment = ""

    def __repr__(self):
        return f"{Move.PLAYERS[self.player]}{self.gtp()}"

    def __eq__(self, other):
        return self.coords == other.coords and self.player == other.player

    def __hash__(self):
        return self.gtp().__hash__()

    def play(self, move):
        try:
            return self.children[self.children.index(move)]
        except ValueError:
            move.parent = self
            self.children.append(move)
            return move

    def temperature(self):
        if self.analysis:
            best_score = float(self.analysis[0]["scoreLead"])
            worst_score = -float(self.pass_analysis[0]["scoreLead"])
            return best_score - worst_score
        else:
            return 0

    def set_analysis(self,analysis_blob,is_pass):
        if is_pass:
            self.pass_analysis = analysis_blob['moveInfos']
        else:
            self.analysis = analysis_blob['moveInfos']
            self.ownership = analysis_blob['ownership']
        if self.analysis and self.pass_analysis:
            if self.parent.analysis:
                self.evaluate()
            for cm in self.children:
                cm.evaluate()

    def evaluate(self):
        previous_move = self.parent
        best_score = float(previous_move.analysis[0]["scoreLead"])
        worst_score = -float(previous_move.pass_analysis[0]["scoreLead"])
        last_move_score = -float(self.analysis[0]["scoreLead"])
        self.previous_temperature = best_score - worst_score
        self.points_lost = best_score - last_move_score
        prev_analysis_current_move = [d for d in previous_move.analysis if d["move"] == self.gtp()]

        if abs(self.previous_temperature) > 0.5:
            self.evaluation = (last_move_score - worst_score) / (best_score - worst_score)
            self.move_options = [previous_move.analysis[0]["scoreLead"]]
        else:
            self.evaluation = None
        if self.evaluation:
            self.comment = f"Evaluation: {100*self.evaluation:.1f}%{' (AI Move)' if self.robot else ''}\n"
            if prev_analysis_current_move:
                self.outdated_evaluation = (prev_analysis_current_move[0]["scoreLead"] - worst_score) / (
                    best_score - worst_score
                )
                self.comment += f"(Was considered last move as: {100 * self.outdated_evaluation:.1f}%)\n"
        else:
            self.comment = "Temperature too low for evaluation\n"
        self.comment += f"Estimate point loss: {self.points_lost:.1f}\n"
        self.comment += f"Last move score was {last_move_score:.1f}\n"
        self.comment += f"Score of top move was {previous_move.analysis[0]['scoreLead']:.1f} @ {previous_move.analysis[0]['move']}\n"
        self.comment += f"Pass score was {worst_score:.1f}\n"

    @property
    def is_pass(self):
        return self.coords[0] is None

    def gtp2ix(self, gtpmove):
        if "pass" in gtpmove:
            return (None, None)
        return Move.GTP_COORD.index(gtpmove[0]), int(gtpmove[1:]) - 1

    def sgf2ix(self, sgfmove_with_board_size):
        sgfmove, board_size = sgfmove_with_board_size
        if sgfmove == "":
            return (None, None)
        return Move.SGF_COORD.index(sgfmove[0]), board_size - Move.SGF_COORD.index(sgfmove[1]) - 1

    def gtp(self):
        if self.is_pass:
            return "pass"
        return Move.GTP_COORD[self.coords[0]] + str(self.coords[1] + 1)

    def sgfcoords(self, board_size):
        return f"{Move.SGF_COORD[self.coords[0]]}{Move.SGF_COORD[board_size - self.coords[1] - 1]}"

    def sgf(self, board_size):
        if self.is_pass:
            return f"{Move.PLAYERS[self.player]}[]"
        else:
            return f"{Move.PLAYERS[self.player]}[{self.sgfcoords(board_size)}]"


class Board:
    _move_id_counter = 0  # used to make a map to all moves across all games

    def __init__(self, board_size=19):
        self.board_size = board_size
        self.root = Move(1, (None, None))  # root is 1=white so black is first
        self.root.id = -1
        self.current_move = self.root
        self.all_moves = {-1: self.root}
        self._init_chains()

    # -- move tree functions --
    def _init_chains(self):
        self.board = [[-1 for x in range(self.board_size)] for y in range(self.board_size)]  # board pos -> chain id
        self.chains = []  # chain id -> chain
        self.prisoners = []
        self.last_capture = []
        try:
            for m in self.moves:
                self._validate_move_and_update_chains(m, True)  # ignore ko since we didn't know if it was forced
        except IllegalMoveException as e:
            raise Exception(f"Unexpected illegal move ({str(e)})")

    def _validate_move_and_update_chains(self, move, ignore_ko):
        def neighbours(moves):
            return {
                self.board[m.coords[1] + dy][m.coords[0] + dx]
                for m in moves
                for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]
                if 0 <= m.coords[0] + dx < self.board_size and 0 <= m.coords[1] + dy < self.board_size
            }

        ko_or_snapback = len(self.last_capture) == 1 and self.last_capture[0] == move
        self.last_capture = []

        if move.is_pass:
            return

        if self.board[move.coords[1]][move.coords[0]] != -1:
            raise IllegalMoveException("Space occupied")

        nb_chains = list({c for c in neighbours([move]) if c >= 0 and self.chains[c][0].player == move.player})
        if nb_chains:
            this_chain = nb_chains[0]
            self.board = [
                [nb_chains[0] if sq in nb_chains else sq for sq in line] for line in self.board
            ]  # merge chains connected by this move
            for oc in nb_chains[1:]:
                self.chains[nb_chains[0]] += self.chains[oc]
                self.chains[oc] = []
            self.chains[nb_chains[0]].append(move)
        else:
            this_chain = len(self.chains)
            self.chains.append([move])
        self.board[move.coords[1]][move.coords[0]] = this_chain

        opp_nb_chains = {c for c in neighbours([move]) if c >= 0 and self.chains[c][0].player != move.player}
        for c in opp_nb_chains:
            if -1 not in neighbours(self.chains[c]):
                self.last_capture += self.chains[c]
                for om in self.chains[c]:
                    self.board[om.coords[1]][om.coords[0]] = -1
                self.chains[c] = []
        if ko_or_snapback and len(self.last_capture) == 1 and not ignore_ko:
            raise IllegalMoveException("Ko")
        self.prisoners += self.last_capture

        if -1 not in neighbours(self.chains[this_chain]):
            raise IllegalMoveException("Suicide")

    # Play a Move from the current position, returns false if invalid.
    def play(self, move, ignore_ko=False):
        try:
            self._validate_move_and_update_chains(move, ignore_ko)
        except IllegalMoveException as e:
            self._init_chains()  # restore
            raise

        move = self.current_move.play(move)  # traverse or append
        if not move.id:
            move.id = Board._move_id_counter
            Board._move_id_counter += 1
        self.all_moves[move.id] = move
        self.current_move = move
        return move

    def undo(self):
        if self.current_move != self.root:
            self.current_move = self.current_move.parent
        self._init_chains()

    @property
    def moves(self) -> list:  # flat list of moves to current
        moves = []
        p = self.current_move
        while p != self.root:
            moves.append(p)
            p = p.parent
        return moves[::-1]

    @property
    def current_player(self):
        return 1 - self.current_move.player

    # --analysis

    def store_analysis(self, json):
        if json["id"].startswith("PASS_"):
            id = int(json["id"].lstrip("PASS_"))
            is_pass = True
        else:
            id = int(json["id"])
            is_pass = False
        move = self.all_moves.get(id)
        if move:  # else this should be old
            move.set_analysis(json,is_pass)
        else:
            print("WARNING: ORPHANED ANALYSIS FOUND - RECENT NEW GAME?")

    # -- board visualization etc
    # ko: single capture and
    # other not allowed: suicide

    @property
    def stones(self):
        return sum(self.chains, [])

    def sgf(self):
        return "SGF[]"

    def __str__(self):
        return (
            "\n".join("".join("BW"[self.chains[c][0].player] if c >= 0 else "-" for c in l) for l in self.board)
            + f"\ncaptures: {self.prisoners}"
        )
