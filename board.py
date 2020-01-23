from move import Move


class IllegalMoveException(Exception):
    pass


class Board:
    _move_id_counter = 0  # used to make a map to all moves across all games

    def __init__(self, board_size=19):
        self.board_size = board_size
        self.root = Move(1, (None, None))  # root is 1=white so black is first
        self.root.id = -1
        self.current_move = self.root
        self.all_moves = {}
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
        return self.current_move.player

    # --analysis

    def store_analysis(self, json):
        if json["id"].starts_with("PASS_"):
            id = int(json["id"].lstrip("PASS_"))
        else:
            id = int(json["id"])
        move = self.all_moves.get(id)
        if move:  # else this should be old
            move.set_analysis(json)
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
