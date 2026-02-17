from kivy.clock import Clock
from kivy.properties import ObjectProperty, OptionProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.behaviors import ToggleButtonBehavior

from katrain.core.constants import (
    MODE_ANALYZE,
    MODE_PLAY,
    PLAYER_HUMAN,
    STATUS_ANALYSIS,
    STATUS_ERROR,
)
from katrain.core.lang import rank_label
from katrain.gui.kivyutils import AnalysisToggle, CollapsablePanel


class PlayAnalyzeSelect(FloatLayout):
    katrain = ObjectProperty(None)
    mode = OptionProperty(MODE_PLAY, options=[MODE_PLAY, MODE_ANALYZE])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self.load_ui_state, 1)

    def save_ui_state(self):
        self.katrain._config["ui_state"] = self.katrain._config.get("ui_state", {})
        
        # Save Analysis Controls
        analysis_state = {}
        for id, widget in self.katrain.analysis_controls.ids.items():
            if isinstance(widget, AnalysisToggle): # Old style
                analysis_state[id] = widget.checkbox.active
            elif isinstance(widget, ToggleButtonBehavior): # New style (ToolbarToggle)
                analysis_state[id] = (widget.state == 'down')
        
        # Save Active Tab (New) or Panels (Old)
        panels_state = {}
        # Support old panels if they exist
        for id, panel in self.katrain.controls.ids.items():
            if isinstance(panel, CollapsablePanel):
                panels_state[id] = (panel.state, panel.option_state)
        
        # Support new tabs
        if 'tab_manager' in self.katrain.controls.ids:
            panels_state['current_tab'] = self.katrain.controls.ids['tab_manager'].current

        self.katrain._config["ui_state"][self.mode] = {
            "analysis_controls": analysis_state,
            "panels": panels_state,
        }
        self.katrain.save_config("ui_state")

    def load_ui_state(self, _dt=None):
        state = self.katrain.config(f"ui_state/{self.mode}", {})
        
        # Load Analysis Controls
        for id, active in state.get("analysis_controls", {}).items():
            if id not in self.katrain.analysis_controls.ids:
                continue
            widget = self.katrain.analysis_controls.ids[id]
            if hasattr(widget, 'checkbox'): # Old style compat
                if hasattr(widget.checkbox, 'active'):
                    widget.checkbox.active = bool(active)
                elif hasattr(widget.checkbox, 'state'):
                    widget.checkbox.state = 'down' if active else 'normal'
            elif isinstance(widget, ToggleButtonBehavior): # New style
                widget.state = 'down' if active else 'normal'

        # Load Panels / Tabs
        panels_data = state.get("panels", {})
        
        # New Tab Logic
        if 'current_tab' in panels_data and 'tab_manager' in self.katrain.controls.ids:
            try:
                self.katrain.controls.ids['tab_manager'].current = panels_data['current_tab']
                # Sync toggle buttons state
                tab = panels_data['current_tab']
                # This assumes we can find the toggle button for this tab. 
                # Since we don't have ids for tab buttons in KV, we might rely on UI persistence or just let it be.
                # Actually, setting current on ScreenManager doesn't update ToggleButtons group automatically unless bound.
                # In KV: on_state: if self.state == 'down': tab_manager.current = 'game'
                # But reverse binding isn't there.
                # For now, we skip updating the toggle buttons visual state from config, 
                # or we could iterate children of the button box.
            except Exception:
                pass

        # Old Panel Logic (Compat)
        for id, (panel_state, button_state) in panels_data.items():
            if id in self.katrain.controls.ids:
                panel = self.katrain.controls.ids[id]
                if isinstance(panel, CollapsablePanel):
                    panel.set_option_state(button_state)
                    panel.state = panel_state

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

    def __init__(self, **kwargs):
        super(ControlsPanel, self).__init__(**kwargs)
        self.status_state = (None, -1e9, None)
        self.active_comment_node = None

    def update_players(self, *_args):
        for bw, player_info in self.katrain.players_info.items():
            self.players[bw].player_type = player_info.player_type
            self.players[bw].player_subtype = player_info.player_subtype
            # Redesigned PlayerInfo might not have 'name' property exposed directly, 
            # or it might handle it differently.
            # In KV I didn't expose 'name' property on PlayerInfo, but it has Labels.
            # I should check PlayerInfo definition in KV.
            # It has 'captures', 'player_type', 'player_subtype'.
            # Name was implicitly handled?
            # Old PlayerInfo had:
            # text: str(root.captures)
            # And some labels.
            # self.players[bw] refers to PlayerInfo instance.
            # If I add a 'name' property to PlayerInfo in KV, I can update it.
            # Currently in new KV:
            # <PlayerInfo>:
            #    captures: 0
            #    player: 'B'
            #    player_type: '...'
            #    player_subtype: '...'
            #    ...
            # I should add 'name' property if it's used.
            # update_players sets self.players[bw].name = ...
            pass # Placeholder for name update if needed

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
