import time

from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.properties import ObjectProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout

from katrain.core.lang import i18n
from katrain.core.constants import MODE_PLAY, MODE_ANALYZE


class PlayAnalyzeSelect(MDFloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def play_analyze_mode(self):
        return MODE_PLAY if self.play.active else MODE_ANALYZE

    def select_mode(self, mode):
        if self.play_analyze_mode != mode:
            self.switch_mode()

    def switch_mode(self):  # TODO: load settings
        if self.play_analyze_mode == MODE_PLAY:
            self.analyze.trigger_action(duration=0)
        else:
            self.play.trigger_action(duration=0)


class ControlsPanel(BoxLayout):
    katrain = ObjectProperty(None)
    button_controls = ObjectProperty(None)

    def __init__(self, **kwargs):
        super(ControlsPanel, self).__init__(**kwargs)
        self.status_msg = None
        self.status_node = None
        self.active_comment_node = None
        self.last_timer_update = (None, 0, False)
        self.beep = SoundLoader.load('beep.wav')
        self.beep_start = 3.2
        self.timer_interval = 0.07

        Clock.schedule_interval(self.update_timer, self.timer_interval)

    def update_players(self, *_args):
        for bw, player_info in self.katrain.players_info.items():
            self.players[bw].player_type = player_info.player_type
            self.players[bw].player_subtype = player_info.player_subtype

    def set_status(self, msg, at_node=None):
        self.status_msg = msg
        self.status_node = at_node or self.katrain and self.katrain.game and self.katrain.game.current_node
        self.status.text = msg
        self.update_evaluation()

    # handles showing completed analysis and score graph
    def update_evaluation(self):
        katrain = self.katrain
        game = katrain and katrain.game
        if not game:
            return
        current_node, move = game.current_node, game.current_node.move
        if game.current_node is not self.status_node and not (
            self.status is not None and self.status_node is None and game.current_node.is_root
        ):  # startup errors on root
            self.status.text = ""
            self.status_node = None

        last_player_was_ai_playing_human = katrain.last_player_info.ai and katrain.next_player_info.human
        both_players_are_robots = katrain.last_player_info.ai and katrain.next_player_info.ai

        self.active_comment_node = current_node
        if katrain.play_analyze_mode == MODE_PLAY and last_player_was_ai_playing_human:
            if katrain.next_player_info.being_taught and current_node.children and current_node.children[-1].auto_undo:
                self.active_comment_node = current_node.children[-1]
            elif current_node.parent:
                self.active_comment_node = current_node.parent
        elif both_players_are_robots and not current_node.analysis_ready and current_node.parent:
            self.active_comment_node = current_node.parent

        lock_ai = katrain.config("trainer/lock_ai") and katrain.play_analyze_mode == MODE_PLAY
        hints = katrain.analysis_controls.hints.active and not lock_ai
        info = ""
        if current_node.move and not current_node.is_root:
            info = self.active_comment_node.comment(
                teach=katrain.players_info[self.active_comment_node.player].being_taught, hints=hints
            )

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

    def update_timer(self, _dt):
        current_node = self.katrain and self.katrain.game and self.katrain.game.current_node
        if current_node:
            last_update_node, last_update_time, beeping = self.last_timer_update
            new_beeping = beeping
            now = time.time()
            byo_len = max(1, self.katrain.config("timer/byo_length"))
            byo_num = max(1, self.katrain.config("timer/byo_periods"))
            sounds_on = self.katrain.config("timer/sound")
            player = self.katrain.next_player_info
            ai = player.ai
            used_period = False

            if not self.timer.paused and not ai and self.katrain.play_analyze_mode == MODE_PLAY:
                if last_update_node == current_node and not current_node.children:
                    current_node.time_used += now - last_update_time
                else:
                    current_node.time_used = 0
                    new_beeping = False
                time_remaining = byo_len - current_node.time_used
                while time_remaining < 0 and player.periods_used < byo_num:
                    current_node.time_used -= byo_len
                    time_remaining += byo_len
                    player.periods_used += 1
                    used_period = True
                if self.beep_start - 2 * self.timer_interval < time_remaining < self.beep_start and player.periods_used < byo_num:
                    new_beeping = True
                elif time_remaining > self.beep_start:
                    new_beeping = False
            else:
                new_beeping = False


            if player.periods_used == byo_num:
                time_remaining = 0
            else:
                time_remaining = byo_len - current_node.time_used
            periods_rem = byo_num - player.periods_used

            if sounds_on:
                if beeping and not new_beeping and not used_period:
                    self.beep.stop()
                elif not beeping and new_beeping and self.beep:
                    self.beep.volume = 0.5 if periods_rem > 1 else 1
                    self.beep.play()

            self.last_timer_update = (current_node, now, new_beeping)

            self.timer.state = (max(0, time_remaining), max(0, periods_rem), ai)
