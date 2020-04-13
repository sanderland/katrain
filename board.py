import os
import random
from datetime import datetime
import copy
from sgfparser import Move, SGFNode, SGF
from typing import List


class IllegalMoveException(Exception):
    pass


class KaTrainSGFNode(SGFNode):
    _node_id_counter = -1

    def __init__(self, parent=None, properties=None, move=None):
        super().__init__(parent=parent, properties=properties, move=move)
        KaTrainSGFNode._node_id_counter += 1
        self.id = KaTrainSGFNode._node_id_counter

        self.analysis = None
        self.pass_analysis = None
        self.ownership = None
        self.x_comment = {}
        self.auto_undid = False
        self.move_number = 0
        self.undo_threshold = random.random()  # for fractional undos, store the random threshold in the move itself for consistency

    @property
    def sgf_properties(self):
        best_sq = []
        properties = copy.copy(super().sgf_properties)
        if best_sq and "SQ" not in properties:
            properties["SQ"] = best_sq
        comment = self.comment(sgf=True)
        if comment:
            properties["C"] = properties.get("C","") + comment
        return properties

    def update_top_move_evaluation(self):  # a move's outdated analysis
        if self.analysis and self.parent and self.parent.analysis:
            for move_dict in self.parent.analysis:
                if move_dict["move"] == self.gtp():
                    move_dict["outdatedScoreLead"] = move_dict["scoreLead"]
                    move_dict["scoreLead"] = self.analysis[0]["scoreLead"]
                    self.parent.update_top_move_evaluation()
                    return

    # various analysis functions
    def set_analysis(self, analysis_blob, is_pass):
        if is_pass:
            self.pass_analysis = analysis_blob["moveInfos"]
        else:
            self.analysis = analysis_blob["moveInfos"]
            self.ownership = analysis_blob["ownership"]
#            if self.children: # TODO: fix when rootInfos comes in
#                self.children[0].update_top_move_evaluation()
#            self.update_top_move_evaluation()

    @property
    def analysis_ready(self):
        return self.analysis is not None and self.pass_analysis is not None

    def format_score(self, score=None):
        score = score or self.score
        return f"{'B' if score >= 0 else 'W'}+{abs(score):.1f}"

    def comment(self, sgf=False, eval=False, hints=False):
        move = self.move
        if not self.parent or not move:  # root
            return ""

        if eval and not sgf and self.children:  # show undos and on previous move as well while playing
            text = "".join(f"Auto undid move {m.gtp()} ({-self.temperature_stats[2] * (1-m.evaluation):.1f} pt)\n" for m in self.children if m.auto_undid)
            if text:
                text += "\n"
        else:
            text = ""

        text += f"Move {self.depth}: {move.player} {move.gtp()}\n"
        text += "\n".join(self.x_comment.values())

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
                elif not move.is_pass and self.parent.analysis[0]["move"] != move.gtp():
                    if sgf:  # shown in stats anyway
                        text += f"Evaluation: {self.evaluation:.1%} efficient\n"
                    outdated_evaluation, outdated_details = self.outdated_evaluation
                    if outdated_evaluation and outdated_evaluation > self.evaluation and outdated_evaluation > self.evaluation + 0.05:
                        text += f"(Was considered last move as {outdated_evaluation:.0%})\n"
                    points_lost = self.player_sign(self.parent.next_player) * (prev_best_score - score)
                    if points_lost > 0.5:
                        text += f"Estimated point loss: {points_lost:.1f}\n"
                if eval or sgf:  # show undos on move itself in both sgf and while playing
                    undids = [m.gtp() + (f"({m.evaluation_info[0]:.1%} efficient)" if m.evaluation_info[0] else "") for m in self.parent.children if m != self]
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
        best = self.analysis[0]["scoreLead"]
        worst = self.pass_analysis[0]["scoreLead"]
        return best, worst, max(self.player_sign(self.next_player) * (best - worst), 0)

    @property
    def score(self):
        return self.temperature_stats[0]

    @staticmethod
    def player_sign(player):
        return {"B": 1, "W": -1, None: 0}[player]

    # need parent analysis ready
    @property
    def evaluation(self):
        best, worst, temp = self.parent.temperature_stats
        return self.player_sign(self.parent.next_player) * (self.score - worst) / temp if temp > 0 else None

    @property
    def outdated_evaluation(self):
        def outdated_score(move_dict):
            return move_dict.get("outdatedScoreLead") or move_dict["scoreLead"]

        prev_analysis_current_move = [d for d in self.parent.analysis if d["move"] == self.move.gtp()]
        if prev_analysis_current_move:
            best_score = outdated_score(self.parent.analysis[0])
            worst_score = self.parent.pass_analysis[0]["scoreLead"]
            prev_temp = max(self.player_sign(self.parent.next_player) * (best_score - worst_score), 0)
            score = outdated_score(prev_analysis_current_move[0])
            return (self.player_sign(self.parent.next_player) * (score - worst_score) / prev_temp if prev_temp > 0 else None), prev_analysis_current_move
        else:
            return None, None

    @property
    def ai_moves(self):
        if not self.analysis_ready:
            return []
        _, worst_score, temperature = self.temperature_stats
        analysis = copy.copy(self.analysis)  # not deep, so eval is saved, but avoids race conditions
        for d in analysis:
            if temperature > 0.5:
                d["evaluation"] = self.player_sign(self.next_player) * (d["scoreLead"] - worst_score) / temperature
            else:
                d["evaluation"] = int(self.player_sign(self.next_player) * d["scoreLead"] >= self.player_sign(self.next_player) * self.analysis[0]["scoreLead"])
        return analysis


class Board:
    def __init__(self, board_size=19, move_tree=None):
        self.game_id = datetime.strftime(datetime.now(), "%Y-%m-%d %H %M %S")
        self.board_size = board_size
        if move_tree:
            self.root = move_tree
        else:
            self.root = KaTrainSGFNode(properties={"RU": "JP", "SZ": board_size})  # TODO: Komi, etc?
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
    _MOVE_CLASS = KaTrainSGFNode
