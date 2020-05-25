import time

from kivy.clock import Clock
from kivy.properties import ObjectProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivymd.uix.boxlayout import MDBoxLayout

from katrain.core.common import MODE_PLAY, MODE_ANALYZE
from katrain.gui.popups import ConfigTeacherPopup, ConfigTimerPopup
from katrain.gui.ai_settings import ConfigAIPopupContents


class RightButtonControls(MDBoxLayout):
    button_size = ListProperty([100, 33])


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
        return MODE_ANALYZE  # ??

    # handles showing completed analysis and score graph
    def update_evaluation(self):
        katrain = self.katrain
        game = katrain and katrain.game
        if not game:
            return
        current_node, move = game.current_node, game.current_node.move
        if game.current_node is not self.status_node and not (self.status is not None and self.status_node is None and game.current_node.is_root):  # startup errors on root
            self.status.text = ""
            self.status_node = None

        both_players_are_robots = all(p.ai for p in game.players.values())
        last_player_was_ai_playing_human = game.last_player.ai and game.next_player.human

        self.active_comment_node = current_node
        if self.play_analyze_mode == MODE_PLAY and last_player_was_ai_playing_human:
            if game.next_player.being_taught and current_node.children and current_node.children.auto_undo:
                self.active_comment_node = current_node.children[-1]
            elif current_node.parent:
                self.active_comment_node = current_node.parent

        hints = katrain.analysis_controls.hints.active
        info = ""
        if current_node.move and not current_node.is_root:
            info = self.active_comment_node.comment(teach=game.players[self.active_comment_node.player].being_taught, hints=hints)

        if self.active_comment_node.analysis_ready:
            self.stats.score = self.active_comment_node.format_score() or ""
            self.stats.winrate = self.active_comment_node.format_winrate() or ""
            self.stats.points_lost = self.active_comment_node.points_lost
            self.stats.player = self.active_comment_node.player
        else:
            self.stats.score = ""
            self.stats.winrate = ""
            self.stats.points_lost = None
            self.stats.player = ""

        self.graph.update_value(current_node)
        self.note.text = current_node.note
        self.info.text = info

    def configure_ais(self):
        if not self.ai_settings_popup:  # persist state of popup etc
            self.ai_settings_popup = Popup(title="Edit AI Settings", size_hint=(0.7, 0.8)).__self__
            self.ai_settings_popup.add_widget(ConfigAIPopupContents(self.katrain, self.ai_settings_popup, self.katrain.config("ai")))
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
            byo_len = max(1, self.katrain.config("timer/byo_length"))
            byo_num = max(1, self.katrain.config("timer/byo_num"))
            player = self.katrain.game.next_player
            ai = player.ai
            if not self.timer.paused and not ai:
                if last_update_node == current_node and not current_node.children:
                    current_node.time_used += now - last_update_time
                else:
                    current_node.time_used = 0
                time_remaining = byo_len - current_node.time_used
                while time_remaining < 0:
                    current_node.time_used -= byo_len
                    time_remaining += byo_len
                    player.periods_used += 1
            time_remaining = byo_len - current_node.time_used
            periods_rem = byo_num - player.periods_used
            self.timer.state = (time_remaining, periods_rem, ai)

    def configure_timer(self):
        self.pause.state = "down"
        if not self.timer_settings_popup:
            self.timer_settings_popup = Popup(title="Edit Timer Settings", size_hint=(0.4, 0.4)).__self__
            self.timer_settings_popup.add_widget(ConfigTimerPopup(self.katrain, self.timer_settings_popup))
        self.timer_settings_popup.open()
