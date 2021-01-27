import time

from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.properties import ObjectProperty, OptionProperty
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.floatlayout import MDFloatLayout

from katrain.core.constants import MODE_ANALYZE, MODE_PLAY, PLAYER_HUMAN, STATUS_ANALYSIS, STATUS_ERROR
from katrain.core.lang import rank_label
from katrain.gui.kivyutils import AnalysisToggle, CollapsablePanel
from katrain.gui.theme import Theme


class PlayAnalyzeSelect(MDFloatLayout):
    katrain = ObjectProperty(None)
    mode = OptionProperty(MODE_PLAY, options=[MODE_PLAY, MODE_ANALYZE])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self.load_ui_state, 1)

    def save_ui_state(self):
        self.katrain._config["ui_state"] = self.katrain._config.get("ui_state", {})
        self.katrain._config["ui_state"][self.mode] = {
            "analysis_controls": {
                id: toggle.active if not toggle.checkbox.slashed else None  # troolean ftw
                for id, toggle in self.katrain.analysis_controls.ids.items()
                if isinstance(toggle, AnalysisToggle)
            },
            "panels": {
                id: (panel.state, panel.option_state)
                for id, panel in self.katrain.controls.ids.items()
                if isinstance(panel, CollapsablePanel)
            },
        }
        self.katrain.save_config("ui_state")

    def load_ui_state(self, _dt=None):
        state = self.katrain.config(f"ui_state/{self.mode}", {})
        for id, active in state.get("analysis_controls", {}).items():
            cb = self.katrain.analysis_controls.ids[id].checkbox
            cb.active = bool(active)
            if cb.tri_state:
                cb.slashed = active is None
        for id, (panel_state, button_state) in state.get("panels", {}).items():
            self.katrain.controls.ids[id].set_option_state(button_state)
            self.katrain.controls.ids[id].state = panel_state

    def select_mode(self, new_mode):  # actual switch state handler
        if self.mode == new_mode:
            return
        self.save_ui_state()
        self.mode = new_mode
        self.katrain.controls.timer_or_movetree.mode = self.mode
        self.load_ui_state()
        self.katrain.update_state()  # for lock ai even if nothing changed

    def switch_ui_mode(self):  # on tab press, fake ui click and trigger everything top down
        if self.mode == MODE_PLAY:
            Clock.schedule_once(
                lambda _dt: self.analyze.trigger_action(duration=0)
            )  # normal trigger does not cross thread
        else:
            Clock.schedule_once(lambda _dt: self.play.trigger_action(duration=0))


class ControlsPanel(BoxLayout):
    katrain = ObjectProperty(None)
    button_controls = ObjectProperty(None)

    def __init__(self, **kwargs):
        super(ControlsPanel, self).__init__(**kwargs)
        self.status_state = (None, -1e9, None)
        self.active_comment_node = None
        self.last_timer_update = (None, 0, False)
        self.beep = SoundLoader.load(Theme.COUNTDOWN_SOUND)
        self.boing = SoundLoader.load(Theme.MINIMUM_TIME_PASSED_SOUND)
        if self.boing:
            self.boing.volume = 0.1
        self.beep_start = 5.2
        self.timer_interval = 0.07

        Clock.schedule_interval(self.update_timer, self.timer_interval)

    def update_players(self, *_args):
        for bw, player_info in self.katrain.players_info.items():
            self.players[bw].player_type = player_info.player_type
            self.players[bw].player_subtype = player_info.player_subtype
            self.players[bw].name = player_info.name
            self.players[bw].rank = (
                player_info.sgf_rank
                if player_info.player_type == PLAYER_HUMAN
                else rank_label(player_info.calculated_rank)
            )

    def set_status(self, msg, status_type, at_node=None, check_level=True):
        at_node = at_node or self.katrain and self.katrain.game and self.katrain.game.current_node
        if (
            at_node != self.status_state[2]
            or not check_level
            or int(status_type) >= int(self.status_state[1])
            or msg == ""
        ):
            if self.status_state != (msg, status_type, at_node):  # prevent loop if error in update eval
                Clock.schedule_once(self.update_evaluation, 0)
            self.status_state = (msg, status_type, at_node)
            self.status.text = msg
            self.status.error = status_type == STATUS_ERROR

    # handles showing completed analysis and score graph
    def update_evaluation(self, *_args):
        katrain = self.katrain
        game = katrain and katrain.game
        if not game:
            return
        current_node, move = game.current_node, game.current_node.move
        if (
            game.current_node is not self.status_state[2]
            and not (self.status_state[1] == STATUS_ERROR and self.status_state[2] is None)
        ) or (
            len(game.engines["B"].queries) == 0 and self.status_state[1] == STATUS_ANALYSIS
        ):  # clear status if node changes, except startup errors on root. also clear analysis message when no queries
            self.status.text = ""
            self.status_state = (None, -1e9, None)

        last_player_was_ai_playing_human = katrain.last_player_info.ai and katrain.next_player_info.human
        both_players_are_robots = katrain.last_player_info.ai and katrain.next_player_info.ai

        self.active_comment_node = current_node
        if katrain.play_analyze_mode == MODE_PLAY and last_player_was_ai_playing_human:
            if katrain.next_player_info.being_taught and current_node.children and current_node.children[-1].auto_undo:
                self.active_comment_node = current_node.children[-1]
            elif current_node.parent:
                self.active_comment_node = current_node.parent
        elif both_players_are_robots and not current_node.analysis_exists and current_node.parent:
            self.active_comment_node = current_node.parent

        lock_ai = katrain.config("trainer/lock_ai") and katrain.play_analyze_mode == MODE_PLAY
        details = self.info.detailed and not lock_ai
        info = ""
        if move or current_node.is_root:
            info = self.active_comment_node.comment(
                teach=katrain.players_info[self.active_comment_node.player].being_taught, details=details
            )

        if self.active_comment_node.analysis_exists:
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
        game = self.katrain and self.katrain.game
        current_node = game and self.katrain.game.current_node
        if current_node:
            last_update_node, last_update_time, beeping = self.last_timer_update
            new_beeping = beeping
            now = time.time()
            main_time = self.katrain.config("timer/main_time", 0) * 60
            byo_len = max(1, self.katrain.config("timer/byo_length"))
            byo_num = max(1, self.katrain.config("timer/byo_periods"))
            sounds_on = self.katrain.config("timer/sound")
            player = self.katrain.next_player_info
            ai = player.ai
            used_period = False

            min_use = self.katrain.config("timer/minimal_use", 0)
            boing_at_remaining = byo_len - min_use
            main_time_remaining = main_time - game.main_time_used

            if not self.timer.paused and not ai and self.katrain.play_analyze_mode == MODE_PLAY:
                if last_update_node == current_node and not current_node.children:
                    if main_time_remaining > 0:
                        game.main_time_used += now - last_update_time
                    else:
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

                if (
                    self.beep_start - 2 * self.timer_interval < time_remaining < self.beep_start
                    and player.periods_used < byo_num
                ):
                    new_beeping = True
                elif time_remaining > self.beep_start:
                    new_beeping = False

                if (
                    min_use
                    and not new_beeping
                    and self.boing
                    and boing_at_remaining - self.timer_interval
                    < time_remaining
                    < boing_at_remaining + self.timer_interval
                    and player.periods_used < byo_num
                ):
                    self.boing.play()

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

            if main_time_remaining > 0:
                self.timer.state = (main_time_remaining, None, ai)
            else:
                self.timer.state = (max(0, time_remaining), max(0, periods_rem), ai)
