import numpy as np
from move import Move


class Board:
    _move_id_counter = 0 # used to make a map to all moves across all games

    def __init__(self, board_size = 19):
        self.board_size = board_size
        self.root = Move(None, (None, None))
        self.current_move = self.root
        self.all_moves = {}
        self.board = np.empty( (self.board_size,self.board_size ) ) # values are indexes in `chains`
        self.board.fill(np.nan)
        self.chains = [] # cache of chain id


# -- move tree functions --
    def update_board(self,move):
        def neighbours_ix(cs):
            return {(x + dx, y + dy) for x, y in cs for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)] if x + dx >= 0 and y + dy >= 0 and y + dy < self.board_size and x + dx < self.board_size}

        def neighbours(cs):
            return {self.board[y][x] for x, y in neighbours_ix(cs)}

        nb_chains = list({int(c) for c in neighbours([move.coords]) if not np.isnan(c) and self.chains[int(c)][0].player == move.player})
        if nb_chains:
            self.board[move.coords[1], move.coords[0]] = nb_chains[0]
            self.board[np.isin(self.board, nb_chains)] = nb_chains[0]
            for oc in nb_chains[1:]:
                self.chains[nb_chains[0]] += self.chains[oc]
                self.chains[oc] = []
            self.chains[nb_chains[0]].append(move)
        else:
            self.board[move.coords[1], move.coords[0]] = len(self.chains)
            self.chains.append([move])
        opp_nb_chains = {int(c) for c in neighbours([move.coords]) if self.chains[int(c)][0].player != move.player}
        capture = False
        for c in opp_nb_chains:
            if np.nan not in neighbours([m.coords for m in self.chains[c]]):
                capture = True
                for om in self.chains[c]:
                    self.board[om.coords[1], om.coords[0]] = np.nan
                self.chains[c] = []
        if not capture:
            if np.nan not in neighbours([m.coords for m in self.chains[c]]):



    # Play a Move from the current position, returns false if invalid.
    def play(self, move) -> bool:





        move = self.current_move.play(move) # traverse or append
        if not move.id:
            move.id = Board._move_id_counter
            Board._move_id_counter += 1
        self.all_moves[move.id] = move
        self.current_move = move
        return True

    def undo(self):
        if self.current_move != self.root:
            self.current_move = self.current_move.parent

    def moves(self) -> list:  # flat list of moves to current
        moves = []
        p = self.current_move
        while p != self.root:
            moves.append(p)
            p = p.parent
        return moves[::-1]


    def __iter__(self):
        return self.moves.__iter__()

    def __getitem__(self, ix):
        if ix == -1:
            return self.current_move
        else:
            return self.moves[ix]

    def current_player(self):
        return self.current_move.player

# --analysis

    def store_analysis(self,json):
        id = int(json["id"])
        move = self.all_moves.get(id)
        if move: # else this should be old
            move.set
        else:
            print("WARNING: ORPHANED ANALYSIS FOUND - RECENT NEW GAME?")

# -- board visualization etc
    # ko: single capture and
    # other not allowed: suicide

    # todo - factor into global state etc? for valid move, cached etc
    @property
    def stones(self):
        board = np.empty( (self.board_size,self.board_size ) )
        def neighbours_ix(cs):
            return {(x+dx,y+dy) for x,y in cs for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)] if x+dx >=0 and y+dy >=0 and y+dy < self.board_size and x+dx < self.board_size}
        def neighbours(cs):
            return {board[y][x] for x,y in neighbours_ix(cs) if not np.isnan(board[y][x]) }

        board.fill(np.nan)
        moves = self.moves()
        chains = []
        for m in moves:
            nb_chains = list({int(c) for c in neighbours([m.coords]) if chains[int(c)][0].player==m.player})
            if nb_chains:
                board[m.coords[1],m.coords[0]] = nb_chains[0]
                board[ np.isin(board,nb_chains) ] = nb_chains[0]
                for oc in nb_chains[1:]:
                    chains[nb_chains[0]] += chains[oc]
                    chains[oc] = []
                chains[nb_chains[0]].append(m)
            else:
                board[m.coords[1],m.coords[0]] = len(chains)
                chains.append([m])
            opp_nb_chains = {int(c) for c in neighbours([m.coords]) if chains[int(c)][0].player != m.player}
            for c in opp_nb_chains:
                if np.nan not in neighbours([m.coords for m in chains[c]]):
                    for om in chains[c]:
                        board[om.coords[1],om.coords[0]] = np.nan
                    chains[c] = []
        return chains

    def sgf(self):
        return "SGF[]"

if __name__ == "__main__":
    b=Board(9)
    b.play(Move(gtpcoords="A3",player=0))
    b.play(Move(gtpcoords="A9",player=0))
    b.play(Move(gtpcoords="B9",player=0))
    b.play(Move(gtpcoords="A4",player=0))
    b.play(Move(gtpcoords="C8",player=0))
    b.play(Move(gtpcoords="C9",player=0))
    print(b.stones)
    b.play(Move(gtpcoords="J9",player=1))
    b.play(Move(gtpcoords="J8", player=0))
    print(b.stones)
    b.play(Move(gtpcoords="H9", player=0))
    print(b.stones)
    b.play(Move(gtpcoords="J9", player=0))
    print(b.stones)

