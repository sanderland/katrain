import copy
import json
import os
import random
import re
import sys
import threading
import time

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.checkbox import CheckBox
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label


class Controls(GridLayout):
    def __init__(self, **kwargs):
        super(Controls, self).__init__(**kwargs)

    def set_status(self, msg):
        self.info.text = msg

    def show_evaluation_stats(self, node):
        if node.analysis_ready:
            self.score.text = node.format_score().replace("-", "\u2013")
            self.win_rate.text = node.format_win_rate()
            if node.points_lost is not None:
                self.points_lost.text = f"{node.points_lost:.1f}"
            else:
                self.points_lost.text = f"?"

    # handles showing completed analysis and triggered actions like auto undo and ai move
    def update_evaluation(self):
        current_node = self.parent.game.current_node
        move = current_node.single_move
        self.score.set_prisoners(self.parent.game.prisoner_count)
        current_player_is_human_or_both_robots = True  # move not self.ai_auto.active(current_node.player) or self.ai_auto.active(1 - current_node.player) # TODO FIX

        if current_player_is_human_or_both_robots and not current_node.is_root:
            self.info.text = current_node.comment(eval=True, hints=self.hints.active(move.player))
        self.points_lost.text = ""
        if current_player_is_human_or_both_robots:
            self.show_evaluation_stats(current_node)

        if False: # TODO: UNDO AND AI MOVE
            if current_node.analysis_ready and current_node.parent and current_node.parent.analysis_ready and not current_node.children and not current_node.x_comment.get("undo"):
                # handle automatic undo
                if self.auto_undo.active(move.player) and not self.ai_auto.active(move.player) and not current_node.auto_undid:
                    ts = self.train_settings
                    # TODO: is this overly generous wrt low visit outdated evaluations?
                    evaluation = current_node.evaluation if current_node.evaluation is not None else 1  # assume move is fine if temperature is negative
                    move_eval = max(evaluation, current_node.outdated_evaluation or 0)
                    points_lost = (current_node.parent or current_node).temperature_stats[2] * (1 - move_eval)
                    if move_eval < ts["undo_eval_threshold"] and points_lost >= ts["undo_point_threshold"]:
                        if self.num_undos(current_node) == 0:
                            current_node.x_comment["undid"] = f"Move was below threshold, but no undo granted (probability is {ts['num_undo_prompts']:.0%}).\n"
                            self.update_evaluation()
                        else:
                            current_node.auto_undid = True
                            self.parent.game.undo()
                            if len(current_node.parent.children) >= ts["num_undo_prompts"] + 1:
                                best_move = sorted([m for m in current_node.parent.children], key=lambda m: -(m.evaluation_info[0] or 0))[0]
                                best_move.x_comment["undo_autoplay"] = f"Automatically played as best option after max. {ts['num_undo_prompts']} undo(s).\n"
                                self.parent.game.play(best_move)
                            self.update_evaluation()
                            return
                # ai player doesn't technically need parent ready, but don't want to override waiting for undo
                current_node = self.parent.game.current_node  # this effectively checks undo didn't just happen
                if self.ai_auto.active(move.opponent) and not self.parent.game.game_ended:
                    if current_node.children:
                        self.info.text = "AI paused since moves were undone. Press 'AI Move' or choose a move for the AI to continue playing."
                    else:
                        self._do_aimove()