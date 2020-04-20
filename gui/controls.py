from kivy.graphics.vertex_instructions import SmoothLine, Line
from kivy.uix.boxlayout import BoxLayout
from kivy.graphics.context_instructions import Color


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

    def unlock(self):
        if self.ai_lock.active:
            self.ai_lock.checkbox.trigger_action(duration=0)
        for el in [self.ai_lock.checkbox, self.analyze_tab_button, self.ai_auto.white, self.ai_auto.black, self.ai_move]:
            el.disabled = False

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
            current_player_is_human_or_both_robots = not current_node.player or not self.ai_auto.active(current_node.player) or self.ai_auto.active(current_node.next_player)
            if current_player_is_human_or_both_robots and not current_node.is_root and move:
                info += current_node.comment(eval=True, hints=self.hints.active(move.player))
            if current_player_is_human_or_both_robots:
                self.show_evaluation_stats(current_node)

            game_node = katrain.game.current_node
            scores = [n.score for n in game_node.nodes_from_root]
            # TODO: like redo, what is the node to redo / should we append? cache?
            self.graph.canvas.clear()
            with self.graph.canvas:
                pt = []
                nnscores = [s for s in scores if s is not None] + [-5, 5]
                scale = max(max(*nnscores), -min(*nnscores)) * 1.05
                xscale = self.graph.width * 0.9 / max(len(scores), 20)
                ls = 0
                for i, s in enumerate(scores):
                    ls = s or ls
                    pt.extend([self.graph.pos[0] + 0.05 * self.graph.width + i * xscale, self.graph.pos[1] + self.graph.height / 2 * (1 + ls / scale)])
                Color(0, 0, 0)
                Line(points=pt, width=1.0)  # just set points?

        self.info.text = info
