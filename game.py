import os
from datetime import datetime

from game_node import GameNode
from sgf_parser import Move, SGF
from typing import List


class IllegalMoveException(Exception):
    pass


class Game:
    GAME_COUNTER = 0

    def __init__(self, katrain, engine, analysis_options, board_options, board_size=None, move_tree=None):
        Game.GAME_COUNTER += 1
        self.katrain = katrain
        self.engine = engine
        self.analysis_options = analysis_options
        self.board_options = board_options
        self.board_size = board_size or self.board_options.get('size',19)
        self.komi = self.board_options.get(f"komi_{self.board_size}",6.5)
        self.game_id = datetime.strftime(datetime.now(), "%Y-%m-%d %H %M %S")

        self.visits = [
            [analysis_settings["pass_visits"], analysis_settings["visits"], analysis_settings["analyze_all_visits"]],
            [analysis_settings["pass_visits_fast"], analysis_settings["visits_fast"], analysis_settings["analyze_all_visits_fast"]],
        ]
        self.train_settings = Config.get("trainer")

        if move_tree:
            self.root = move_tree
        else:
            self.root = GameNode(properties={"RU": "JP", "SZ": self.board_size, "KM": self.komi,
                                                   "PC": "KaTrain: https://github.com/sanderland/katrain",
                                                   "DT": self.game_id})
        self.current_node = self.root
        self._node_by_id = {m.id: m for m in self.root.nodes_in_tree}
        self._init_chains()

    # -- move tree functions --
    def _init_chains(self):
        self.board = [[-1 for _x in range(self.board_size)] for _y in range(self.board_size)]  # type: List[list[int]]  #  board pos -> chain id
        self.chains = []  # type: List[List[Move]]  #   chain id -> chain
        self.prisoners = []  # type: List[Move]
        self.last_capture = []  # type: List[Move]
        try:
            #            for m in self.moves:
            for node in self.current_node.nodes_from_root:
                for m in node.move_with_placements:
                    self._validate_move_and_update_chains(m, True)  # ignore ko since we didn't know if it was forced
        except IllegalMoveException as e:
            raise Exception(f"Unexpected illegal move ({str(e)})")

    def _validate_move_and_update_chains(self, move: Move, ignore_ko: bool):
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
    def play(self, move: Move, ignore_ko: bool = False):
        if not move.is_pass and not (0 <= move.coords[0] < self.board_size and 0 <= move.coords[1] < self.board_size):
            raise IllegalMoveException(f"Move {move} outside of board coordinates")
        played_node = self.current_node.play(move)
        try:
            self._validate_move_and_update_chains(played_node.move, ignore_ko)
        except IllegalMoveException:
            self.current_node.children = [m for m in self.current_node.children if m != played_node]
            self._init_chains()  # restore
            raise
        self._node_by_id[played_node.id] = played_node
        self.current_node = played_node
        return played_node

    def undo(self):
        if self.current_node is not self.root:
            self.current_node = self.current_node.parent
        self._init_chains()

    def redo(self):
        if self.current_node.children:
            self.play(self.current_node.children[-1])

    def switch_branch(self, direction):
        cm = self.current_node  # avoid race conditions
        if cm.parent and len(cm.parent.children) > 1:
            ix = cm.parent.children.index(cm)
            self.current_node = cm.parent.children[(ix + direction) % len(cm.parent.children)]
            self._init_chains()

    def place_handicap_stones(self, n_handicaps):
        near = 3 if self.board_size >= 13 else 2
        far = self.board_size - 1 - near
        middle = self.board_size // 2
        stones = [(far, far), (near, near), (far, near), (near, far)]
        if n_handicaps % 2 == 1:
            stones.append((middle, middle))
        stones += [(near, middle), (far, middle), (middle, near), (middle, far)]
        self.root["AB"] = [Move(stone).sgf(board_size=self.board_size) for stone in stones[:n_handicaps]]

    #    @property
    #    def moves(self) -> list:  # flat list of moves to current, including placements
    #        return sum([node.move_with_placements for node in self.current_node.nodes_from_root],[])

    @property
    def next_player(self):
        return self.current_node.next_player

    def store_analysis(self, json):
        if json["id"].startswith("AA:"):  # board sweep analyze all
            _, move_id, gtpcoords = json["id"].split(":")
            move = self._node_by_id.get(int(move_id))
            if not move.analysis:
                return  # should have been prevented, but better not to crash
            cur_analysis = [d for d in move.analysis if d["move"] == gtpcoords]
            move_analysis = {k: v for k, v in json["moveInfos"][0].items() if k not in {"move", "pv"}}
            move_analysis["visits"] = sum(d["visits"] for d in json["moveInfos"])  # TODO: ??
            if cur_analysis:
                if cur_analysis[0]["visits"] < move_analysis["visits"]:
                    cur_analysis[0].update(move_analysis)
            else:
                move.analysis.append({"move": gtpcoords, **move_analysis})
            return

        if json["id"].startswith("PASS_"):
            move_id = int(json["id"].lstrip("PASS_"))
            is_pass = True
        else:
            move_id = int(json["id"])
            is_pass = False
        move = self._node_by_id.get(move_id)
        if move:  # else this should be old
            move.set_analysis(json, is_pass)
        else:
            print("WARNING: ORPHANED ANALYSIS FOUND - RECENT NEW GAME?")

    @property
    def stones(self):
        return sum(self.chains, [])

    @property
    def game_ended(self):
        return self.current_node.parent and self.current_node.is_pass and self.current_node.parent.is_pass

    @property
    def prisoner_count(self):
        return [sum([m.player == player for m in self.prisoners]) for player in Move.PLAYERS]

    def __repr__(self):
        return "\n".join("".join(Move.PLAYERS[self.chains[c][0].player] if c >= 0 else "-" for c in line) for line in self.board) + f"\ncaptures: {self.prisoner_count}"

    def write_sgf(self, file_name=None):
        file_name = file_name or f"sgfout/katrain_{self.game_id}.sgf"
        os.makedirs(os.path.dirname(file_name), exist_ok=True)
        with open(file_name, "w") as f:
            f.write(self.root.sgf())
        return f"SGF with analysis written to {file_name}"


class KaTrainSGF(SGF):
    _MOVE_CLASS = GameNode
