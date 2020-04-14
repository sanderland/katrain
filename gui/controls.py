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
from kivy.uix.popup import Popup




class Controls(GridLayout):
    def __init__(self, **kwargs):
        super(Controls, self).__init__(**kwargs)

    def set_status(self, msg):
        self.info.text = msg

    def show_evaluation_stats(self, move):
        if move.analysis_ready:
            self.score.text = move.format_score().replace("-", "\u2013")
            self.temperature.text = f"{move.temperature_stats[2]:.1f}"
            if move.parent and move.parent.analysis_ready:
                if move.evaluation is not None:
                    self.evaluation.text = f"{move.evaluation:.1%}"
                else:
                    self.evaluation.text = f"?"

    # handles showing completed analysis and triggered actions like auto undo and ai move
    def update_evaluation(self):
        current_node = self.parent.game.current_node
        move = current_node.move
        self.score.set_prisoners(self.parent.game.prisoner_count)
        current_player_is_human_or_both_robots = True  # move not self.ai_auto.active(current_node.player) or self.ai_auto.active(1 - current_node.player) # TODO FIX

        if current_player_is_human_or_both_robots and not current_node.is_root:
            self.info.text = current_node.comment(eval=True, hints=self.hints.active(move.player))
        self.evaluation.text = ""
        if current_player_is_human_or_both_robots:
            self.show_evaluation_stats(current_node)

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
        self.redraw(include_board=False)

    # engine action functions


    def _do_aimove(self):
        ts = self.train_settings
        while not self.parent.game.current_node.analysis_ready:
            self.info.text = "Thinking..."
            self.ai_thinking = True
            time.sleep(0.05)
        self.ai_thinking = False
        # select move
        current_move = self.parent.game.current_node
        pos_moves = [
            (d["move"], float(d["scoreLead"]), d["evaluation"]) for i, d in enumerate(current_move.ai_moves) if i == 0 or int(d["visits"]) >= ts["balance_play_min_visits"]
        ]
        sel_moves = pos_moves[:1]
        # don't play suicidal to balance score - pass when it's best
        if self.ai_balance.active and pos_moves[0][0] != "pass":
            sel_moves = [
                (move, score, move_eval)
                for move, score, move_eval in pos_moves
                if move_eval > ts["balance_play_randomize_eval"]
                and -current_move.player_sign * score > 0
                or move_eval > ts["balance_play_min_eval"]
                and -current_move.player_sign * score > ts["balance_play_target_score"]
            ] or sel_moves
        aimove = Move.from_gtp(random.choice(sel_moves)[0], player=self.parent.game.next_player)
        if len(sel_moves) > 1:
            aimove.x_comment["ai"] = "AI Balance on, moves considered: " + ", ".join(f"{move} ({aimove.format_score(score)})" for move, score, _ in sel_moves) + "\n"
        self.play(aimove)

    def num_undos(self, move):
        if self.train_settings["num_undo_prompts"] < 1:
            return int(move.undo_threshold < self.train_settings["num_undo_prompts"])
        else:
            return self.train_settings["num_undo_prompts"]

    def _do_undo(self):
        if (
            self.ai_lock.active
            and self.auto_undo.active(self.parent.game.current_node.player)
            and len(self.parent.game.current_node.parent.children) > self.num_undos(self.parent.game.current_node)
            and not self.train_settings.get("dont_lock_undos")
        ):
            self.info.text = f"Can't undo this move more than {self.num_undos(self.parent.game.current_node)} time(s) when locked"
            return
        self.parent.game.undo()
        self.update_evaluation()

    def _do_redo(self):
        self.parent.game.redo()
        self.update_evaluation()

    def _do_redo_branch(self, direction):
        self.parent.game.switch_branch(direction)
        self.update_evaluation()

    def _do_init(self, board_size=None, komi=None, move_tree=None):
        self.game_counter += 1  # prioritize newer games
        self.parent.game_size = board_size or 19
        self.komi = float(komi or self.config.get("board").get(f"komi_{board_size}", 6.5))
        self.parent.game = Game(board_size, move_tree)
        self._request_analysis(self.parent.game.root, priority=self.game_counter)
        self.redraw(include_board=True)
        self.ready = True
        if self.ai_lock.active:
            self.ai_lock.checkbox._do_press()
        for el in [self.ai_lock.checkbox, self.hints.black, self.hints.white, self.ai_auto.black, self.ai_auto.white, self.auto_undo.black, self.auto_undo.white, self.ai_move]:
            el.disabled = False

    def _do_analyze_extra(self, mode):
        stones = {s.coords for s in self.parent.game.stones}
        current_move = self.parent.game.current_node
        if not current_move.analysis:
            self.info.text = "Wait for initial analysis to complete before doing a board-sweep or refinement"
            return
        played_moves = self.parent.game.moves

        if mode == "extra":
            visits = sum([d["visits"] for d in current_move.analysis]) + self.visits[0][1]
            self.info.text = f"Performing additional analysis to {visits} visits"
            self._request_analysis(current_move, min_visits=visits, priority=self.game_counter - 1_000)
            return
        elif mode == "sweep":
            analyze_moves = [SGFNode(coords=(x, y)).gtp() for x in range(self.parent.game_size) for y in range(self.parent.game_size) if (x, y) not in stones]
            visits = self.visits[self.ai_fast.active][2]
            self.info.text = f"Refining analysis of entire board to {visits} visits"
            priority = self.game_counter - 1_000_000_000
        else:  # mode=='refine':
            analyze_moves = [a["move"] for a in current_move.analysis]
            visits = current_move.analysis[0]["visits"] + self.visits[1][2]
            self.info.text = f"Refining analysis of candidate moves to {visits} visits"
            priority = self.game_counter - 1_000

        for gtpcoords in analyze_moves:
            self._send_analysis_query(
                {
                    "id": f"AA:{current_move.id}:{gtpcoords}",
                    "moves": [[m.bw_player(), m.gtp()] for m in played_moves] + [[current_move.bw_player(True), gtpcoords]],
                    "includeOwnership": False,
                    "maxVisits": visits,
                    "priority": priority,
                }
            )

    def analyze_movetree(self, root, faster=False):
        self._do_init(root["SZ"], root["KM"])
        self.parent.game.root = root
        handicap = root["HA"]
        if handicap is not None and root["AB"] is None:
            self.parent.game.place_handicap_stones(handicap)
        analysis_priority = self.game_counter - 1_000_000
        for move in self.parent.game.root.moves_in_tree:
            self._request_analysis(move, faster=faster, priority=analysis_priority)  # ensure next move analysis works

    def _do_analyze_sgf(self, sgf):
        try:
            root = KaTrainSGF.parse(sgf)
        except:
            root = GameNode()
        if root.empty:
            fileselect_popup = Popup(title="Double Click SGF file to analyze", size_hint=(0.8, 0.8))
            fc = FileChooserListView(multiselect=False, path=os.path.expanduser(self.config.get("sgf")["load"]), filters=["*.sgf"])
            blui = BoxLayout(orientation="horizontal", size_hint=(1, 0.1))
            cbfast = CheckBox(color=(0.95, 0.95, 0.95, 1))
            cbrewind = CheckBox(color=(0.95, 0.95, 0.95, 1), active=True)
            for widget in [Label(text="Analyze Extra Fast"), cbfast, Label(text="Rewind to start"), cbrewind]:
                blui.add_widget(widget)
            bl = BoxLayout(orientation="vertical")
            bl.add_widget(fc)
            bl.add_widget(blui)
            fileselect_popup.add_widget(bl)

            def readfile(files, _mouse):
                fileselect_popup.dismiss()
                self.analyze_movetree(KaTrainSGF.parse_file(files[0]))

            fc.on_submit = readfile
            fileselect_popup.open()
            return
        else:
            self.analyze_movetree(root)


    def output_sgf(self):
        for pl in Move.PLAYERS:
            if self.parent.game.root[f"P{pl}"] not in ["KaTrain","Player",None,""]:
                self.parent.game.root[f"P{pl}"] = "KaTrain" if self.ai_auto.active(pl) else "Player"
        return self.parent.game.write_sgf(self.komi)
