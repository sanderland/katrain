import math

from kivy.properties import ListProperty, NumericProperty

from katrain.gui.kivyutils import BackgroundColor


class ScoreGraph(BackgroundColor):
    nodes = ListProperty([])
    score_points = ListProperty([])
    winrate_points = ListProperty([])
    dot_pos = ListProperty([0, 0])
    highlighted_index = NumericProperty(None)
    y_scale = NumericProperty(5)
    highlight_size = NumericProperty(5)

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

    def update_graph(self, *args):
        nodes = self.nodes
        if nodes:
            values = [n.score if n and n.score else math.nan for n in nodes]
            nn_values = [n.score for n in nodes if n and n.score]
            val_range = min(nn_values or [0]), max(nn_values or [0])

            self.y_scale = math.ceil(max(5, max(-val_range[0], val_range[1])) / 5) * 5

            xscale = self.width / max(len(values) - 1, 15)
            available_height = self.height
            line_points = [[self.pos[0] + i * xscale, self.pos[1] + self.height / 2 + available_height / 2 * (val / self.y_scale)] for i, val in enumerate(values)]
            self.score_points = sum(line_points, [])
            self.winrate_points = self.score_points  # TODO

            if self.highlighted_index is not None:
                self.highlighted_index = min(self.highlighted_index, len(values) - 1)
                dot_point = line_points[self.highlighted_index]
                if math.isnan(dot_point[1]):
                    dot_point[1] = self.pos[1] + self.height / 2 + available_height / 2 * ((nn_values or [0])[-1] / self.y_scale)
                self.dot_pos = [c - self.highlight_size / 2 for c in dot_point]

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
