import time

from kivy.clock import Clock
from kivy.properties import ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from katrain.core.common import PLAYER_HUMAN, PLAYER_AI, PLAYER_HUMAN_TEACHING
from katrain.gui.popups import ConfigAIPopup, ConfigTeacherPopup, ConfigTimerPopup


class ControlsPanel(BoxLayout):
    katrain = ObjectProperty(None)
    button_controls = ObjectProperty(None)

    def __init__(self, **kwargs):
        super(ControlsPanel, self).__init__(**kwargs)
        self.status_msg = None
        self.status_node = None
        self.ai_settings_popup = None
        self.teacher_settings_popup = None
        self.active_comment_node = None
        self.timer_settings_popup = None
        self.last_timer_update = (None, 0)
        self.periods_used = {"B": 0, "W": 0}
        Clock.schedule_interval(self.update_timer, 0.07)

    def check_hide_show(self, *_args):
        pass

    def set_status(self, msg, at_node=None):
        self.status_msg = msg
        self.status_node = at_node or self.katrain and self.katrain.game and self.katrain.game.current_node
        self.status.text = msg
        self.update_evaluation()

    @property
    def play_analyze_mode(self):
        return "analyze"  # ??

    def player_mode(self, player):
        return PLAYER_HUMAN

    def ai_mode(self, player):
        return self.ai_mode_groups[player].text

    def teaching_mode_enabled(self):
        return PLAYER_HUMAN_TEACHING in [self.player_mode("B"), self.player_mode("W")]

    def on_size(self, *args):
        self.update_evaluation()

    # handles showing completed analysis and score graph
    def update_evaluation(self):
        katrain = self.katrain
        current_node = katrain and katrain.game and katrain.game.current_node

        if current_node is not self.status_node and not (self.status is not None and self.status_node is None and current_node.is_root):  # startup errors on root
            self.status.text = ""
            self.status_node = None

        info = ""

        if current_node:
            move = current_node.move
            both_players_are_robots = self.player_mode(current_node.player) == PLAYER_AI and self.player_mode(current_node.next_player) == PLAYER_AI
            next_player_is_human_or_both_robots = current_node.player and (self.player_mode(current_node.player) == PLAYER_AI or both_players_are_robots)
            current_player_is_ai_playing_human = (
                current_node.player and self.player_mode(current_node.player) == PLAYER_AI and self.player_mode(current_node.next_player) != PLAYER_AI
            )
            if next_player_is_human_or_both_robots and not current_node.is_root and move:
                info += current_node.comment(teach=self.player_mode(current_node.player) == PLAYER_HUMAN_TEACHING, hints=self.hints.active)
                self.active_comment_node = current_node
            elif current_player_is_ai_playing_human and current_node.parent:
                info += current_node.parent.comment(teach=self.player_mode(current_node.next_player) == PLAYER_HUMAN_TEACHING, hints=self.hints.active)
                self.active_comment_node = current_node.parent

            if current_node.analysis_ready:
                self.stats.score.text = current_node.format_score()
                self.stats.win_rate.text = current_node.format_win_rate()
                if move and next_player_is_human_or_both_robots:  # don't immediately hide this when an ai moves comes in
                    points_lost = current_node.points_lost
                    self.stats.score_change.label = f"Points lost" if points_lost and points_lost > 0 else f"Points gained"
                    self.stats.score_change.text = f"{move.player}: {abs(points_lost):.1f}" if points_lost else "-"
                elif not current_player_is_ai_playing_human:
                    self.stats.score_change.label = f"Points lost"
                    self.stats.score_change.text = "-"
            elif current_player_is_ai_playing_human and current_node.parent and current_node.parent.move:
                points_lost = current_node.parent.points_lost
                self.stats.score_change.label = f"Points lost" if points_lost and points_lost > 0 else f"Points gained"
                self.stats.score_change.text = f"{current_node.parent.move.player}: {abs(points_lost):.1f}" if points_lost else "-"
            elif both_players_are_robots and current_node.parent and current_node.parent.analysis_ready:
                self.stats.score.text = current_node.parent.format_score()
                self.stats.win_rate.text = current_node.parent.format_win_rate()

            self.graph.update_value(current_node)
            self.note.text = current_node.note
        self.info.text = info

    def configure_ais(self):
        if not self.ai_settings_popup:  # persist state of popup etc
            self.ai_settings_popup = Popup(title="Edit AI Settings", size_hint=(0.7, 0.8)).__self__
            self.ai_settings_popup.add_widget(ConfigAIPopup(self.katrain, self.ai_settings_popup, self.katrain.config("ai")))
        self.ai_settings_popup.open()

    def configure_teacher(self):
        if not self.teacher_settings_popup:
            self.teacher_settings_popup = Popup(title="Edit Teacher Settings", size_hint=(0.7, 0.8)).__self__
            self.teacher_settings_popup.add_widget(ConfigTeacherPopup(self.katrain, self.teacher_settings_popup))
        self.teacher_settings_popup.open()

    def update_timer(self, _dt):
        current_node = self.katrain and self.katrain.game and self.katrain.game.current_node
        if current_node:
            last_update_node, last_update_time = self.last_timer_update
            now = time.time()
            self.last_timer_update = (current_node, now)
            player = current_node.next_player
            byo_len = max(1, self.katrain.config("timer/byo_length"))
            byo_num = max(1, self.katrain.config("timer/byo_num"))
            ai = self.player_mode(player) == PLAYER_AI
            if not self.timer.paused and not ai:
                if last_update_node == current_node and not current_node.children:
                    current_node.time_used += now - last_update_time
                else:
                    current_node.time_used = 0
                time_remaining = byo_len - current_node.time_used
                while time_remaining < 0:
                    current_node.time_used -= byo_len
                    time_remaining += byo_len
                    self.periods_used[player] += 1
            time_remaining = byo_len - current_node.time_used
            periods_rem = byo_num - self.periods_used[player]
            self.timer.state = (time_remaining, periods_rem, ai)

    def configure_timer(self):
        self.pause.state = "down"
        if not self.timer_settings_popup:
            self.timer_settings_popup = Popup(title="Edit Timer Settings", size_hint=(0.4, 0.4)).__self__
            self.timer_settings_popup.add_widget(ConfigTimerPopup(self.katrain, self.timer_settings_popup))
        self.timer_settings_popup.open()