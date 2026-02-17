from kivy.clock import Clock
from kivy.properties import ObjectProperty, OptionProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout

from katrain.core.constants import (
    MODE_ANALYZE,
    MODE_PLAY,
    PLAYER_HUMAN,
    STATUS_ANALYSIS,
    STATUS_ERROR,
)
from katrain.core.lang import rank_label
from katrain.gui.kivyutils import AnalysisToggle


class PlayAnalyzeSelect(FloatLayout):
    katrain = ObjectProperty(None)
    mode = OptionProperty(MODE_PLAY, options=[MODE_PLAY, MODE_ANALYZE])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self.load_ui_state, 1)

    def save_ui_state(self):
        self.katrain._config["ui_state"] = self.katrain._config.get("ui_state", {})
        self.katrain._config["ui_state"][self.mode] = {
            "analysis_controls": {
                id: toggle.active
                for id, toggle in self.katrain.analysis_controls.ids.items()
                if isinstance(toggle, AnalysisToggle)
            },
            "sidebar": {
                "view": getattr(self.katrain.controls, "sidebar_view", "info"),
                "info_detailed": bool(getattr(self.katrain.controls.info, "detailed", False)),
            },
        }
        self.katrain.save_config("ui_state")

    def load_ui_state(self, _dt=None):
        state = self.katrain.config(f"ui_state/{self.mode}", {})
        for id, active in state.get("analysis_controls", {}).items():
            cb = self.katrain.analysis_controls.ids[id].checkbox
            cb.active = bool(active)

        sidebar = state.get("sidebar", {})
        if "view" in sidebar:
            self.katrain.controls.sidebar_view = sidebar["view"]
        if "info_detailed" in sidebar:
            self.katrain.controls.info.detailed = bool(sidebar["info_detailed"])

    def select_mode(self, new_mode):  # actual switch state handler
        if self.mode == new_mode:
            return
        self.save_ui_state()
        self.mode = new_mode
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
    sidebar_view = OptionProperty("info", options=["info", "graph", "stats"])

    def __init__(self, **kwargs):
        super(ControlsPanel, self).__init__(**kwargs)
        self.status_state = (None, -1e9, None)
        self.active_comment_node = None

    def set_sidebar_view(self, view: str) -> None:
        self.sidebar_view = view

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
            self.katrain.engine.is_idle() and self.status_state[1] == STATUS_ANALYSIS
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

        details = self.info.detailed
        info = ""

        if move or current_node.is_root:
            info += self.active_comment_node.comment(
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
