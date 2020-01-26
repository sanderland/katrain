class IllegalMoveException(Exception):
    pass


class Move:
    GTP_COORD = "ABCDEFGHJKLMNOPQRSTUVWYXYZ"
    PLAYERS = "BW"
    SGF_COORD = [chr(i) for i in range(97, 123)]
    _move_id_counter = -1

    def __init__(self, player, coords=None, gtpcoords=None, sgfcoords=None, robot=False):
        Move._move_id_counter += 1
        self.id = Move._move_id_counter
        self.player = player
        self.coords = coords or (gtpcoords and self.gtp2ix(gtpcoords)) or self.sgf2ix(sgfcoords)
        self.children = []
        self.parent = None
        self.robot = robot
        self.analysis = None
        self.pass_analysis = None
        self.ownership = None
        self.x_comment = ""
        self.auto_undid = False
        self.move_number = 0

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
            move.move_number = self.move_number + 1
            self.children.append(move)
            return move

    @property
    def is_pass(self):
        return self.coords[0] is None

    # various analysis functions
    def set_analysis(self, analysis_blob, is_pass):
        if is_pass:
            self.pass_analysis = analysis_blob["moveInfos"]
        else:
            self.analysis = analysis_blob["moveInfos"]
            self.ownership = analysis_blob["ownership"]

    @property
    def analysis_ready(self):
        return self.analysis and self.pass_analysis

    def format_score(self, score=None):
        score = score or self.score
        return f"{'B' if score >= 0 else 'W'}+{abs(score):.1f}"

    def comment(self, sgf=False, eval=False, hints=False):
        if not self.parent:  # root
            return ""
        text = f"Move {self.move_number}: {self.bw_player()} {self.gtp()}  {'(AI Move)' if self.robot else ''}\n"
        text += self.x_comment

        if eval and not sgf:  # show undos and on previous move as well while playing
            text += "".join(f"Auto undid move {m.gtp()} ({m.evaluation*100:.1f}% efficient)\n" for m in self.children if m.auto_undid)

        if self.analysis_ready:
            score, _, temperature = self.temperature_stats
            if sgf:
                text += f"Score: {self.format_score(score)}\n"
            if self.parent and self.parent.analysis_ready:
                prev_best_score, prev_worst_score, prev_temperature = self.parent.temperature_stats
                if sgf or hints:
                    text += f"Top move was {self.parent.analysis[0]['move']} ({self.format_score(prev_best_score)})\n"
                    text += f"Pass score was {self.format_score(prev_worst_score)}\n"
                    text += f"Previous temperature: {prev_temperature:.1f}\n"
                if prev_temperature < 0.5:
                    text += f"Previous temperature ({prev_temperature:.1f}) too low for evaluation\n"
                elif not self.is_pass:
                    if sgf or eval:
                        text += f"Evaluation: {100*self.evaluation:.1f}% efficient\n"
                        outdated_evaluation = self.outdated_evaluation
                        if outdated_evaluation and outdated_evaluation > self.evaluation and outdated_evaluation > self.evaluation + 0.01:
                            text += f"(Was considered last move as: {100 * outdated_evaluation :.1f}%)\n"
                        points_lost = self.player_sign * (prev_best_score - score)
                        if points_lost > 0.5:
                            text += f"Estimate point loss: {points_lost:.1f}\n"

        if eval or sgf:  # show undos on move itself in both sgf and while playing
            undids = [m.gtp() + (f"({m.evaluation_info[0]*100:.1f}% efficient)" if m.evaluation_info[0] else "") for m in self.parent.children if m != self]
            if undids:
                text += "Other attempted move(s): " + ", ".join(undids) + "\n"

        else:
            text = "No analysis available" if sgf else "Analyzing move..."
        return text

    # returns evaluation, temperature scale or None, None when not ready
    @property
    def evaluation_info(self):
        if self.parent and self.parent.analysis_ready and self.analysis_ready:
            return self.evaluation, self.parent.temperature_stats[2]
        else:
            return None, None

    # needing own analysis ready
    @property
    def temperature_stats(self):
        best = float(self.analysis[0]["scoreLead"])
        worst = float(self.pass_analysis[0]["scoreLead"])
        return best, worst, abs(best - worst)

    @property
    def score(self):
        return self.temperature_stats[0]

    @property
    def player_sign(self):
        return 1 if self.player == 0 else -1

    # need parent analysis ready
    @property
    def evaluation(self):
        best, worst, temp = self.parent.temperature_stats
        return self.player_sign * (self.score - worst) / temp

    @property
    def outdated_evaluation(self):
        prev_analysis_current_move = [d for d in self.parent.analysis if d["move"] == self.gtp()]
        if prev_analysis_current_move:
            best_score, worst_score, prev_temp = self.parent.temperature_stats
            return self.player_sign * (prev_analysis_current_move[0]["scoreLead"] - worst_score) / prev_temp

    @property
    def ai_moves(self):
        if not self.analysis_ready:
            return []
        _, worst_score, temperature = self.temperature_stats
        for d in self.analysis:
            d["evaluation"] = -self.player_sign * (d["scoreLead"] - worst_score) / temperature
        return self.analysis

    # various output and conversion functions

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

    def bw_player(self, next_move=False):
        return Move.PLAYERS[1 - self.player if next_move else self.player]

    def sgf(self, board_size):
        if self.is_pass:
            return f"{self.bw_player()}[]"
        else:
            return f"{self.bw_player()}[{self.sgfcoords(board_size)}]"


class Board:
    def __init__(self, board_size=19):
        self.board_size = board_size
        self.root = Move(1, (None, None))  # root is 1=white so black is first
        self.current_move = self.root
        self.all_moves = {self.root.id: self.root}
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
            self.board = [[nb_chains[0] if sq in nb_chains else sq for sq in line] for line in self.board]  # merge chains connected by this move
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

    # Play a Move from the current position, raise IllegalMoveException if invalid.
    def play(self, move, ignore_ko=False):
        played_move = self.current_move.play(move)
        try:
            self._validate_move_and_update_chains(played_move, ignore_ko)
        except IllegalMoveException as e:
            self.current_move.children = [m for m in self.current_move.children if m != played_move]
            self._init_chains()  # restore
            raise
        self.all_moves[played_move.id] = played_move
        self.current_move = played_move
        return played_move

    def undo(self):
        if self.current_move is not self.root:
            self.current_move = self.current_move.parent
        self._init_chains()

    @property
    def moves(self) -> list:  # flat list of moves to current
        moves = []
        p = self.current_move
        while p is not self.root:  # NB == is wrong here
            moves.append(p)
            p = p.parent
        return moves[::-1]

    @property
    def current_player(self):
        return 1 - self.current_move.player

    def store_analysis(self, json):
        if json["id"].startswith("PASS_"):
            id = int(json["id"].lstrip("PASS_"))
            is_pass = True
        else:
            id = int(json["id"])
            is_pass = False
        move = self.all_moves.get(id)
        if move:  # else this should be old
            move.set_analysis(json, is_pass)
        else:
            print("WARNING: ORPHANED ANALYSIS FOUND - RECENT NEW GAME?")

    @property
    def stones(self):
        return sum(self.chains, [])

    @property
    def game_ended(self):
        return self.current_move.parent and self.current_move.is_pass and self.current_move.parent.is_pass

    @property
    def prisoner_count(self):
        return [sum([m.player == player for m in self.prisoners]) for player in [0, 1]]

    def __str__(self):
        return "\n".join("".join(Move.PLAYERS[self.chains[c][0].player] if c >= 0 else "-" for c in l) for l in self.board) + f"\ncaptures: {self.prisoner_count}"
