import copy
import random

from sgf_parser import SGFNode


class GameNode(SGFNode):
    _node_id_counter = -1

    def __init__(self, parent=None, properties=None, move=None):
        super().__init__(parent=parent, properties=properties, move=move)
        GameNode._node_id_counter += 1
        self.id = GameNode._node_id_counter

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