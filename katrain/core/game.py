import math
import os
import re
import threading
from datetime import datetime
from typing import Dict, List, Optional, Union

from kivy.clock import Clock

from katrain.core.constants import (
    HOMEPAGE,
    OUTPUT_DEBUG,
    OUTPUT_INFO,
    PLAYER_AI,
    STATUS_ANALYSIS,
    STATUS_INFO,
    STATUS_TEACHING,
)
from katrain.core.engine import KataGoEngine
from katrain.core.game_node import GameNode
from katrain.core.lang import i18n, rank_label
from katrain.core.sgf_parser import SGF, Move
from katrain.core.utils import var_to_grid


class IllegalMoveException(Exception):
    pass


class KaTrainSGF(SGF):
    _NODE_CLASS = GameNode


class Game:
    """Represents a game of go, including an implementation of capture rules."""

    DEFAULT_PROPERTIES = {"GM": 1, "FF": 4, "AP": f"KaTrain:{HOMEPAGE}", "CA": "UTF-8"}

    def __init__(
        self,
        katrain,
        engine: Union[Dict, KataGoEngine],
        move_tree: GameNode = None,
        analyze_fast=False,
        game_properties: Optional[Dict] = None,
    ):
        self.katrain = katrain
        self._lock = threading.Lock()
        if not isinstance(engine, Dict):
            engine = {"B": engine, "W": engine}
        self.engines = engine
        self.game_id = datetime.strftime(datetime.now(), "%Y-%m-%d %H %M %S")

        if move_tree:
            self.root = move_tree
            self.komi = self.root.komi
            handicap = int(self.root.get_property("HA", 0))
            if handicap >= 2 and not self.root.placements:
                self.root.place_handicap_stones(handicap)
        else:
            board_size = katrain.config("game/size")
            self.komi = katrain.config("game/komi")
            self.root = GameNode(
                properties={
                    **Game.DEFAULT_PROPERTIES,
                    **{"SZ": board_size, "KM": self.komi, "DT": self.game_id},
                    **(game_properties or {}),
                }
            )
            handicap = katrain.config("game/handicap")
            if handicap:
                self.root.place_handicap_stones(handicap)

        if not self.root.get_property("RU"):
            self.root.set_property("RU", katrain.config("game/rules"))

        self.set_current_node(self.root)
        threading.Thread(
            target=lambda: self.analyze_all_nodes(-1_000_000, analyze_fast=analyze_fast), daemon=True
        ).start()  # return faster, but bypass Kivy Clock

    def analyze_all_nodes(self, priority=0, analyze_fast=False):
        for node in self.root.nodes_in_tree:
            node.analyze(self.engines[node.next_player], priority=priority, analyze_fast=analyze_fast)

    # -- move tree functions --
    def _calculate_groups(self):
        board_size_x, board_size_y = self.board_size
        with self._lock:
            self.board = [
                [-1 for _x in range(board_size_x)] for _y in range(board_size_y)
            ]  # type: List[List[int]]  #  board pos -> chain id
            self.chains = []  # type: List[List[Move]]  #   chain id -> chain
            self.prisoners = []  # type: List[Move]
            self.last_capture = []  # type: List[Move]
            try:
                for node in self.current_node.nodes_from_root:
                    for m in node.move_with_placements:
                        self._validate_move_and_update_chains(
                            m, True
                        )  # ignore ko since we didn't know if it was forced
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

        if -1 not in neighbours(self.chains[this_chain]):  # TODO: NZ rules?
            raise IllegalMoveException("Suicide")

    # Play a Move from the current position, raise IllegalMoveException if invalid.
    def play(self, move: Move, ignore_ko: bool = False, analyze=True):
        board_size_x, board_size_y = self.board_size
        if not move.is_pass and not (0 <= move.coords[0] < board_size_x and 0 <= move.coords[1] < board_size_y):
            raise IllegalMoveException(f"Move {move} outside of board coordinates")
        try:
            self._validate_move_and_update_chains(move, ignore_ko)
        except IllegalMoveException:
            self._calculate_groups()
            raise
        with self._lock:
            played_node = self.current_node.play(move)
            self.current_node = played_node
        if analyze:
            played_node.analyze(self.engines[played_node.next_player])
        return played_node

    def set_current_node(self, node):
        self.current_node = node
        self._calculate_groups()

    def undo(self, n_times=1):
        cn = self.current_node  # avoid race conditions
        for _ in range(n_times):
            if not cn.is_root:
                cn = cn.parent
        self.set_current_node(cn)

    def redo(self, n_times=1):
        cn = self.current_node  # avoid race conditions
        for _ in range(n_times):
            if cn.children:
                cn = cn.ordered_children[0]
        self.set_current_node(cn)

    def cycle_children(self, direction):
        cn = self.current_node  # avoid race conditions
        if cn.parent and len(cn.parent.children) > 1:
            ordered_children = cn.parent.ordered_children
            ix = (ordered_children.index(cn) + len(ordered_children) + direction) % len(ordered_children)
            self.set_current_node(ordered_children[ix])

    @property
    def board_size(self):
        return self.root.board_size

    @property
    def stones(self):
        with self._lock:
            return sum(self.chains, [])

    @property
    def ended(self):
        return self.current_node.parent and self.current_node.is_pass and self.current_node.parent.is_pass

    @property
    def prisoner_count(
        self,
    ) -> Dict:  # returns prisoners that are of a certain colour as {B: black stones captures, W: white stones captures}
        return {player: sum([m.player == player for m in self.prisoners]) for player in Move.PLAYERS}

    @property
    def manual_score(self):
        rules = self.engines["B"].get_rules(self.root)
        if not self.current_node.ownership or rules != "japanese":
            if not self.current_node.score:
                return None
            self.katrain.log(
                f"rules '{rules}' are not japanese, or no ownership available ({not self.current_node.ownership}) -> no manual score available",
                OUTPUT_DEBUG,
            )
            return self.current_node.format_score(round(2 * self.current_node.score) / 2) + "?"
        board_size_x, board_size_y = self.board_size
        ownership_grid = var_to_grid(self.current_node.ownership, (board_size_x, board_size_y))
        stones = {m.coords: m.player for m in self.stones}
        lo_threshold = 0.15
        hi_threshold = 0.85
        max_unknown = 10
        max_dame = 4 * (board_size_x + board_size_y)

        def japanese_score_square(square, owner):
            player = stones.get(square, None)
            if (
                (player == "B" and owner > hi_threshold)
                or (player == "W" and owner < -hi_threshold)
                or abs(owner) < lo_threshold
            ):
                return 0  # dame or own stones
            if player is None and abs(owner) >= hi_threshold:
                return round(owner)  # surrounded empty intersection
            if (player == "B" and owner < -hi_threshold) or (player == "W" and owner > hi_threshold):
                return 2 * round(owner)  # captured stone
            return math.nan  # unknown!

        scored_squares = [
            japanese_score_square((x, y), ownership_grid[y][x])
            for y in range(board_size_y)
            for x in range(board_size_x)
        ]
        num_sq = {t: sum([s == t for s in scored_squares]) for t in [-2, -1, 0, 1, 2]}
        num_unkn = sum(math.isnan(s) for s in scored_squares)
        prisoners = self.prisoner_count
        score = sum([t * n for t, n in num_sq.items()]) + prisoners["W"] - prisoners["B"] - self.komi
        self.katrain.log(
            f"Manual Scoring: {num_sq} score by square with {num_unkn} unknown, {prisoners} captures, and {self.komi} komi -> score = {score}",
            OUTPUT_DEBUG,
        )
        if num_unkn > max_unknown or (num_sq[0] - len(stones)) > max_dame:
            return None
        return self.current_node.format_score(score)

    def __repr__(self):
        return (
            "\n".join("".join(self.chains[c][0].player if c >= 0 else "-" for c in line) for line in self.board)
            + f"\ncaptures: {self.prisoner_count}"
        )

    def write_sgf(
        self, path: str, trainer_config: Optional[Dict] = None,
    ):
        if trainer_config is None:
            trainer_config = self.katrain.config("trainer")
        save_feedback = trainer_config["save_feedback"]
        eval_thresholds = trainer_config["eval_thresholds"]

        def player_name(player_info):
            return f"{i18n._(player_info.player_type)} ({i18n._(player_info.player_subtype)})"

        if "KaTrain" in self.root.get_property("AP", ""):
            for bw in "BW":
                self.root.set_property("P" + bw, player_name(self.katrain.players_info[bw]))
                player_info = self.katrain.players_info[bw]
                if player_info.player_type == PLAYER_AI:
                    self.root.set_property(bw + "R", rank_label(player_info.calculated_rank))

        player_names = {bw: re.sub(r"['<>:\"/\\|?*]", "", self.root.get_property("P" + bw, bw)) for bw in "BW"}
        game_name = f"katrain_{player_names['B']} vs {player_names['W']} {self.game_id}"
        file_name = os.path.abspath(os.path.join(path, f"{game_name}.sgf"))
        os.makedirs(os.path.dirname(file_name), exist_ok=True)

        show_dots_for = {
            bw: trainer_config.get("eval_show_ai", True) or self.katrain.players_info[bw].human for bw in "BW"
        }
        sgf = self.root.sgf(
            save_comments_player=show_dots_for, save_comments_class=save_feedback, eval_thresholds=eval_thresholds
        )
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(sgf)
        return i18n._("sgf written").format(file_name=file_name)

    def analyze_extra(self, mode, **kwargs):
        stones = {s.coords for s in self.stones}
        cn = self.current_node

        engine = self.engines[cn.next_player]
        Clock.schedule_once(self.katrain.analysis_controls.hints.activate, 0)

        if mode == "extra":
            if kwargs.get("continuous", False):
                visits = max(engine.config["max_visits"], math.ceil(cn.analysis_visits_requested * 1.25))
            else:
                visits = cn.analysis_visits_requested + engine.config["max_visits"]
            self.katrain.controls.set_status(i18n._("extra analysis").format(visits=visits), STATUS_ANALYSIS)
            cn.analyze(engine, visits=visits, priority=-1_000, time_limit=False)
            return
        if mode == "game":
            nodes = self.root.nodes_in_tree
            if "visits" in kwargs:
                visits = kwargs["visits"]
            else:
                min_visits = min(node.analysis_visits_requested for node in nodes)
                visits = min_visits + engine.config["max_visits"]
            for node in nodes:
                node.analyze(engine, visits=visits, priority=-1_000_000, time_limit=False)
            self.katrain.controls.set_status(i18n._("game re-analysis").format(visits=visits), STATUS_ANALYSIS)
            return

        elif mode == "sweep":
            board_size_x, board_size_y = self.board_size
            if cn.analysis_ready:
                policy_grid = (
                    var_to_grid(self.current_node.policy, size=(board_size_x, board_size_y))
                    if self.current_node.policy
                    else None
                )
                analyze_moves = sorted(
                    [
                        Move(coords=(x, y), player=cn.next_player)
                        for x in range(board_size_x)
                        for y in range(board_size_y)
                        if (policy_grid is None and (x, y) not in stones) or policy_grid[y][x] >= 0
                    ],
                    key=lambda mv: -policy_grid[mv.coords[1]][mv.coords[0]],
                )
            else:
                analyze_moves = [
                    Move(coords=(x, y), player=cn.next_player)
                    for x in range(board_size_x)
                    for y in range(board_size_y)
                    if (x, y) not in stones
                ]
            visits = engine.config["fast_visits"]
            self.katrain.controls.set_status(i18n._("sweep analysis").format(visits=visits), STATUS_ANALYSIS)
            priority = -1_000_000_000
        elif mode == "equalize":
            if not cn.analysis_ready:
                self.katrain.controls.set_status(i18n._("wait-before-equalize"), STATUS_INFO, self.current_node)
                return

            analyze_moves = [Move.from_gtp(gtp, player=cn.next_player) for gtp, _ in cn.analysis["moves"].items()]
            visits = max(d["visits"] for d in cn.analysis["moves"].values())
            self.katrain.controls.set_status(i18n._("equalizing analysis").format(visits=visits), STATUS_ANALYSIS)
            priority = -1_000
        else:
            raise ValueError("Invalid analysis mode")
        for move in analyze_moves:
            cn.analyze(
                engine, priority, visits=visits, refine_move=move, time_limit=False
            )  # explicitly requested so take as long as you need

    def analyze_undo(self, node):
        train_config = self.katrain.config("trainer")
        move = node.move
        if node != self.current_node or node.auto_undo is not None or not node.analysis_ready or not move:
            return
        points_lost = node.points_lost
        thresholds = train_config["eval_thresholds"]
        num_undo_prompts = train_config["num_undo_prompts"]
        i = 0
        while i < len(thresholds) and points_lost < thresholds[i]:
            i += 1
        num_undos = num_undo_prompts[i] if i < len(num_undo_prompts) else 0
        if num_undos == 0:
            undo = False
        elif num_undos < 1:  # probability
            undo = int(node.undo_threshold < num_undos) and len(node.parent.children) == 1
        else:
            undo = len(node.parent.children) <= num_undos

        node.auto_undo = undo
        if undo:
            self.undo(1)
            self.katrain.controls.set_status(
                i18n._("teaching undo message").format(move=move.gtp(), points_lost=points_lost), STATUS_TEACHING
            )
            self.katrain.update_state()
