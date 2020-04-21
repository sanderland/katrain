from kivy.graphics.context_instructions import Color
from kivy.graphics.vertex_instructions import Line, SmoothLine
from kivy.uix.boxlayout import BoxLayout


class Controls(BoxLayout):
    def __init__(self, **kwargs):
        super(Controls, self).__init__(**kwargs)
        self.status = None
        self.status_node = None

    def set_status(self, msg, at_node=None):
        self.status = msg
        self.status_node = at_node or self.parent.game and self.parent.game.current_node
        self.info.text = msg
        self.update_evaluation()

    def select_mode(self, mode):
        if mode == "analyze":
            self.analyze_tab_button.trigger_action(duration=0)
        else:
            self.play_tab_button.trigger_action(duration=0)

    def show_evaluation_stats(self, node):
        if node.analysis_ready:
            self.score.text = node.format_score().replace("-", "\u2013")
            self.win_rate.text = node.format_win_rate()
            move = node.single_move
            if move:
                self.points_lost.label = f"Point loss {move.player}{move.gtp()}"
            else:
                self.points_lost.label = f"Point loss"
                self.points_lost.text = ""
                return

            if node.points_lost is not None:
                self.points_lost.text = f"{node.points_lost:.1f}"
            else:
                self.points_lost.text = f"..."

    def player_mode(self, player):
        return self.player_mode_groups[player].value

    def ai_mode(self, player):
        return self.ai_mode_groups[player].text.lower()

    def on_size(self, *args):
        self.update_evaluation()

    # handles showing completed analysis and score graph
    def update_evaluation(self):
        katrain = self.parent
        current_node = katrain.game and katrain.game.current_node

        info = ""
        if current_node is self.status_node or (self.status is not None and self.status_node is None and current_node.is_root):  # startup errors on root
            info += self.status + "\n"
        else:
            self.status_node = None

        if current_node:
            move = current_node.single_move
            current_player_is_human_or_both_robots = (
                not current_node.player or "ai" not in self.player_mode(current_node.player) or "ai" in self.player_mode(current_node.next_player)
            )
            if current_player_is_human_or_both_robots and not current_node.is_root and move:
                info += current_node.comment(eval=True, hints=self.hints.active)
            if current_player_is_human_or_both_robots:
                self.show_evaluation_stats(current_node)

            if current_node.score:
                self.graph.update_value(current_node)

        self.info.text = info
