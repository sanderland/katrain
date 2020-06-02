import math

from kivy.properties import BooleanProperty, ListProperty, NumericProperty

from katrain.gui.kivyutils import BackgroundMixin


class ScoreGraph(BackgroundMixin):
    show_score = BooleanProperty(True)
    show_winrate = BooleanProperty(True)

    nodes = ListProperty([])
    score_points = ListProperty([])
    winrate_points = ListProperty([])

    score_dot_pos = ListProperty([0, 0])
    winrate_dot_pos = ListProperty([0, 0])
    highlighted_index = NumericProperty(None)
    highlight_size = NumericProperty(6)

    score_scale = NumericProperty(5)
    winrate_scale = NumericProperty(5)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self.update_graph, size=self.update_graph)

    def initialize_from_game(self, root):
        self.nodes = [root]
        node = root
        while node.children:
            node = node.favourite_child
            self.nodes.append(node)
        self.highlighted_index = 0

    def show_graphs(self, keys):
        self.show_score = keys["score"]
        self.show_winrate = keys["winrate"]

    def update_graph(self, *args):
        nodes = self.nodes
        if nodes:
            score_values = [n.score if n and n.score else math.nan for n in nodes]
            score_nn_values = [n.score for n in nodes if n and n.score]
            score_values_range = min(score_nn_values or [0]), max(score_nn_values or [0])

            winrate_values = [(n.winrate - 0.5) * 100 if n and n.winrate else math.nan for n in nodes]
            winrate_nn_values = [(n.winrate - 0.5) * 100 for n in nodes if n and n.winrate]
            winrate_values_range = min(winrate_nn_values or [0]), max(winrate_nn_values or [0])

            score_granularity = 5
            winrate_granularity = 10
            self.score_scale = (
                max(math.ceil(max(-score_values_range[0], score_values_range[1]) / score_granularity), 1)
                * score_granularity
            )
            self.winrate_scale = (
                max(math.ceil(max(-winrate_values_range[0], winrate_values_range[1]) / winrate_granularity), 1)
                * winrate_granularity
            )

            xscale = self.width / max(len(score_values) - 1, 15)
            available_height = self.height
            score_line_points = [
                [
                    self.pos[0] + i * xscale,
                    self.pos[1] + self.height / 2 + available_height / 2 * (val / self.score_scale),
                ]
                for i, val in enumerate(score_values)
            ]
            winrate_line_points = [
                [
                    self.pos[0] + i * xscale,
                    self.pos[1] + self.height / 2 + available_height / 2 * (val / self.winrate_scale),
                ]
                for i, val in enumerate(winrate_values)
            ]
            self.score_points = sum(score_line_points, [])
            self.winrate_points = sum(winrate_line_points, [])

            if self.highlighted_index is not None:
                self.highlighted_index = min(self.highlighted_index, len(score_values) - 1)
                score_dot_point = score_line_points[self.highlighted_index]
                winrate_dot_point = winrate_line_points[self.highlighted_index]
                if math.isnan(score_dot_point[1]):
                    score_dot_point[1] = (
                        self.pos[1]
                        + self.height / 2
                        + available_height / 2 * ((score_nn_values or [0])[-1] / self.score_scale)
                    )
                self.score_dot_pos = [c - self.highlight_size / 2 for c in score_dot_point]
                if math.isnan(winrate_dot_point[1]):
                    winrate_dot_point[1] = (
                        self.pos[1]
                        + self.height / 2
                        + available_height / 2 * ((winrate_nn_values or [0])[-1] / self.winrate_scale)
                    )
                self.winrate_dot_pos = [c - self.highlight_size / 2 for c in winrate_dot_point]

    def update_value(self, node):
        self.highlighted_index = index = node.depth
        self.nodes.extend([None] * max(0, index - (len(self.nodes) - 1)))
        self.nodes[index] = node
        if index + 1 < len(self.nodes) and (node is None or self.nodes[index + 1] not in node.children):
            self.nodes = self.nodes[: index + 1]  # on branch switching, don't show history from other branch
        if index == len(self.nodes) - 1:  # possibly just switched branch
            while node.children:  # add children back
                node = node.children[0]
                self.nodes.append(node)
        self.update_graph()
