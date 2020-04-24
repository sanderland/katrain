import math
import os
import random
import re
import time
from datetime import datetime
from typing import List

from kivy.clock import Clock

from common import OUTPUT_DEBUG, OUTPUT_INFO
from game_node import GameNode
from sgf_parser import SGF, Move


class IllegalMoveException(Exception):
    pass


class KaTrainSGF(SGF):
    _NODE_CLASS = GameNode


class Game:
    """Represents a game of go, including an implementation of capture rules."""

    DEFAULT_PROPERTIES = {"GM": 1, "FF": 4, "RU": "JP", "AP": "KaTrain:https://github.com/sanderland/katrain"}

    def __init__(self, katrain, engine, config, move_tree=None):
        self.katrain = katrain
        self.engine = engine
        self.config = config
        self.game_id = datetime.strftime(datetime.now(), "%Y-%m-%d %H %M %S")

        if move_tree:
            self.root = move_tree
            self.komi = self.root.komi
            handicap = self.root.get_first("HA")
            if handicap and not self.root.placements:
                self.place_handicap_stones(handicap)
        else:
            board_size = config["init_size"]
            self.komi = self.config["init_komi"].get(str(board_size), 6.5)
            self.root = GameNode(properties={**Game.DEFAULT_PROPERTIES, **{"SZ": board_size, "KM": self.komi, "DT": self.game_id}})

        self.current_node = self.root
        self._init_chains()

        Clock.schedule_once(lambda _dt: self.analyze_all_nodes(-1_000_000), -1)  # return faster

    def analyze_all_nodes(self, priority=0):
        self.engine.on_new_game()
        for node in self.root.nodes_in_tree:
            node.analyze(self.engine, priority=priority)

    # -- move tree functions --
    def _init_chains(self):
        board_size_x, board_size_y = self.board_size
        self.board = [[-1 for _x in range(board_size_x)] for _y in range(board_size_y)]  # type: List[List[int]]  #  board pos -> chain id
        self.chains = []  # type: List[List[Move]]  #   chain id -> chain
        self.prisoners = []  # type: List[Move]
        self.last_capture = []  # type: List[Move]
        try:
            #            for m in self.moves:
            for node in self.current_node.nodes_from_root:
                for m in node.move_with_placements:  # TODO: placements are never illegal
                    self._validate_move_and_update_chains(m, True)  # ignore ko since we didn't know if it was forced
        except IllegalMoveException as e:
            raise Exception(f"Unexpected illegal move ({str(e)})")

    def _validate_move_and_update_chains(self, move: Move, ignore_ko: bool):
        board_size_x, board_size_y = self.board_size

        def neighbours(moves):
            return {
                self.board[m.coords[1] + dy][m.coords[0] + dx]
                for m in moves
                for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]
                if 0 <= m.coords[0] + dx < board_size_x and 0 <= m.coords[1] + dy < board_size_y
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

        if -1 not in neighbours(self.chains[this_chain]):  # TODO: NZ?
            raise IllegalMoveException("Suicide")

    # Play a Move from the current position, raise IllegalMoveException if invalid.
    def play(self, move: Move, ignore_ko: bool = False):
        board_size_x, board_size_y = self.board_size
        if not move.is_pass and not (0 <= move.coords[0] < board_size_x and 0 <= move.coords[1] < board_size_y):
            raise IllegalMoveException(f"Move {move} outside of board coordinates")
        try:
            self._validate_move_and_update_chains(move, ignore_ko)
        except IllegalMoveException:
            self._init_chains()
            raise
        played_node = self.current_node.play(move)
        self.current_node = played_node
        played_node.analyze(self.engine)
        return played_node

    def undo(self, n_times=1):
        cn = self.current_node  # avoid race conditions
        for _ in range(n_times):
            if not cn.is_root:
                cn = cn.parent
        self.current_node = cn
        self._init_chains()

    def redo(self, n_times=1):
        cn = self.current_node  # avoid race conditions
        for _ in range(n_times):
            if cn.children:
                cn = cn.children[-1]
        self.current_node = cn
        self._init_chains()

    def switch_branch(self, direction):
        cn = self.current_node  # avoid race conditions
        if cn.parent and len(cn.parent.children) > 1:
            ix = cn.parent.children.index(cn)
            self.current_node = cn.parent.children[(ix + direction) % len(cn.parent.children)]
            self._init_chains()

    def place_handicap_stones(self, n_handicaps):
        board_size_x, board_size_y = self.board_size
        near_x = 3 if board_size_x >= 13 else 2
        near_y = 3 if board_size_y >= 13 else 2
        far_x = board_size_x - 1 - near_x
        far_y = board_size_x - 1 - near_x
        middle_x = board_size_x // 2  # what for even sizes?
        middle_y = board_size_y // 2
        if n_handicaps > 9 and board_size_x == board_size_y:
            stones_per_row = math.ceil(math.sqrt(n_handicaps))
            spacing = (far_x - near_x) / (stones_per_row - 1)
            if spacing < near_x:
                far_x += 1
                near_x -= 1
                spacing = (far_x - near_x) / (stones_per_row - 1)
            coords = [math.floor(0.5 + near_x + i * spacing) for i in range(stones_per_row)]
            stones = sorted([(x, y) for x in coords for y in coords], key=lambda xy: -((xy[0] - board_size_x / 2) ** 2 + (xy[1] - board_size_y / 2) ** 2))
        else:  # max 9
            stones = [(far_x, far_y), (near_x, near_y), (far_x, near_y), (near_x, far_y)]
            if n_handicaps % 2 == 1:
                stones.append((middle_x, middle_y))
            stones += [(near_x, middle_y), (far_x, middle_y), (middle_x, near_y), (middle_x, far_y)]
        self.root.add_property("AB", [Move(stone).sgf(board_size=(board_size_x, board_size_y)) for stone in stones[:n_handicaps]])

    @property
    def board_size(self):
        return self.root.board_size

    @property
    def next_player(self):
        return self.current_node.next_player

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

    def write_sgf(self, path=None):
        black = re.sub(r"['<>:\"/\\|?*]", "", self.root.get_first("PB"))
        white = re.sub(r"['<>:\"/\\|?*]", "", self.root.get_first("PW"))
        white = self.root.get_first("PW")
        game_name = f"katrain_{black} vs {white} {self.game_id}"
        file_name = os.path.join(path, f"{game_name}.sgf")
        os.makedirs(os.path.dirname(file_name), exist_ok=True)
        with open(file_name, "w") as f:
            f.write(self.root.sgf())
        return f"SGF with analysis written to {file_name}"

    def analyze_extra(self, mode):
        stones = {s.coords for s in self.stones}
        cn = self.current_node
        if not cn.analysis:
            self.katrain.controls.set_status("Wait for initial analysis to complete before doing a board-sweep or refinement", self.current_node)
            return

        if mode == "extra":
            visits = cn.analysis["root"]["visits"] + self.engine.config["max_visits"]
            self.katrain.controls.set_status(f"Performing additional analysis to {visits} visits")
            cn.analyze(self.engine, visits=visits, priority=-1_000, time_limit=False)
            return
        elif mode == "sweep":
            board_size_x, board_size_y = self.board_size
            analyze_moves = [Move(coords=(x, y), player=cn.next_player) for x in range(board_size_x) for y in range(board_size_y) if (x, y) not in stones]
            visits = int(self.engine.config["max_visits"] * self.config["sweep_visits_frac"] + 0.5)
            self.katrain.controls.set_status(f"Refining analysis of entire board to {visits} visits")
            priority = -1_000_000_000
        else:  # mode=='equalize':
            analyze_moves = [Move.from_gtp(gtp, player=cn.next_player) for gtp, _ in cn.analysis["moves"].items()]
            visits = max(d["visits"] for d in cn.analysis["moves"].values())
            self.katrain.controls.set_status(f"Equalizing analysis of candidate moves to {visits} visits")
            priority = -1_000
        for move in analyze_moves:
            cn.analyze(self.engine, priority, visits=visits, refine_move=move, time_limit=False)  # explicitly requested so take as long as you need

    def analyze_undo(self, node, train_config):
        move = node.single_move
        if node != self.current_node or node.auto_undo is not None or not node.analysis_ready or not move:
            return
        points_lost = node.points_lost
        thresholds = train_config["eval_thresholds"]
        num_undo_prompts = train_config["num_undo_prompts"]
        i = 0
        while i < len(thresholds) and points_lost < thresholds[i]:
            i += 1
        num_undos = num_undo_prompts[i] if i < len(num_undo_prompts) else 0
        xmsg = ". Please try again."
        if num_undos == 0:
            undo = False
        elif num_undos < 1:  # probability
            undo = int(node.undo_threshold < num_undos) and len(node.parent.children) == 1
            xmsg = f" (with {num_undos:.0%} probability at this level of mistake)" + xmsg
        else:
            undo = len(node.parent.children) <= num_undos
            if len(node.parent.children) == num_undos:
                xmsg = xmsg[:-1] + ", but note that this is your last try at this level of mistake."
        node.auto_undo = undo
        if undo:
            self.undo(1)
            self.katrain.controls.set_status(f"Undid move {move.gtp()} as it lost {points_lost:.1f} points{xmsg}")
            self.katrain.update_state()
