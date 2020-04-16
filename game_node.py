import copy
import random
from typing import Dict, List, Optional

from sgf_parser import SGFNode


class GameNode(SGFNode):
    """Represents a single game node, with one or more moves and placements."""

    def __init__(self, parent=None, properties=None, move=None):
        super().__init__(parent=parent, properties=properties, move=move)
        self.analysis = None
        self.ownership = None
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
            properties["C"] = [properties.get("C", "") + comment]
        return properties

    # various analysis functions
    def analyze(self, engine, priority=0):
        engine.request_analysis(self, lambda result: self.set_analysis(result), priority=priority)

    def set_analysis(self, analysis_blob):
        self.analysis = analysis_blob["moveInfos"]  # TODO: fix when rootInfos comes in
        self.ownership = analysis_blob["ownership"]

    @property
    def analysis_ready(self):
        return self.analysis is not None

    def format_score(self, score=None):
        score = score or self.score
        return f"{'B' if score >= 0 else 'W'}+{abs(score):.1f}"

    def format_win_rate(self, win_rate=None):
        win_rate = win_rate or self.analysis[0]['winrate']
        b_adv = win_rate-0.5
        return f"{'B' if b_adv > 0 else 'W'}+{abs(b_adv):.1%}"


    def comment(self, sgf=False, eval=False, hints=False):
        single_move = self.single_move
        if not self.parent or not single_move:  # root
            return ""

        text = f"Move {self.depth}: {single_move.player} {single_move.gtp()}\n"

        if self.analysis_ready:
            score = self.score
            if sgf:
                text += f"Score: {self.format_score(score)}\n"
            if self.parent and self.parent.analysis_ready:
                if sgf or hints:
                    text += f"Top move was {self.parent.analysis[0]['move']} ({self.format_score(self.parent.analysis[0]['scoreLead'])})\n"
                elif self.parent.analysis[0]["move"] != single_move.gtp():
                    points_lost = self.points_lost
                    if points_lost > 0.5:
                        text += f"Estimated point loss: {points_lost:.1f}\n"
        else:
            text = "No analysis available" if sgf else "Analyzing move..."
        return text

    @property
    def points_lost(self) -> Optional[float]:
        single_move = self.single_move
        if single_move and self.parent and self.analysis_ready and self.parent.analysis_ready:
            parent_score = self.parent.score
            score = self.score
            return self.player_sign(single_move.player) * (parent_score - score)

    @property
    def score(self):
        return self.analysis[0]["scoreLead"]  # TODO: update for rootInfo

    @staticmethod
    def player_sign(player):
        return {"B": 1, "W": -1, None: 0}[player]

    @property
    def ai_moves(self) -> List[Dict]:
        if not self.analysis_ready:
            return []
        analysis = copy.copy(self.analysis)  # not deep, so eval is saved, but avoids race conditions
        for d in analysis:
            d["pointsLost"] = self.player_sign(self.next_player) * (analysis[0]["scoreLead"] - d["scoreLead"])  # TODO: update for rootInfo
        return analysis
