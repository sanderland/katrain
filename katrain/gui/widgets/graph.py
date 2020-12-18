import math
import threading

from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, Clock, ListProperty, NumericProperty, StringProperty
from kivy.uix.widget import Widget
from kivymd.app import MDApp

from katrain.gui.theme import Theme


class Graph(Widget):
    marker_font_size = NumericProperty(0)
    background_image = StringProperty(Theme.GRAPH_TEXTURE)
    background_color = ListProperty([1, 1, 1, 1])
    highlighted_index = NumericProperty(0)
    nodes = ListProperty([])
    hidden = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._lock = threading.Lock()
        self.bind(pos=self.update_graph, size=self.update_graph)
        self.redraw_trigger = Clock.create_trigger(self.update_graph, 0.1)

    def initialize_from_game(self, root):
        self.nodes = [root]
        node = root
        while node.children:
            node = node.ordered_children[0]
            self.nodes.append(node)
        self.highlighted_index = 0
        self.redraw_trigger()

    def update_graph(self, *args):
        pass

    def update_value(self, node):
        with self._lock:
            self.highlighted_index = index = node.depth
            self.nodes.extend([None] * max(0, index - (len(self.nodes) - 1)))
            self.nodes[index] = node
            if index > 1 and node.parent:  # sometimes there are gaps
                backfill, bfnode = index - 1, node.parent
                while bfnode is not None and self.nodes[backfill] != bfnode:
                    self.nodes[backfill] = bfnode
                    backfill -= 1
                    bfnode = bfnode.parent

            if index + 1 < len(self.nodes) and (
                node is None or not node.children or self.nodes[index + 1] != node.ordered_children[0]
            ):
                self.nodes = self.nodes[: index + 1]  # on branch switching, don't show history from other branch
            if index == len(self.nodes) - 1:  # possibly just switched branch or the line above triggered
                while node.children:  # add children back
                    node = node.ordered_children[0]
                    self.nodes.append(node)
            self.redraw_trigger()


class ScoreGraph(Graph):
    show_score = BooleanProperty(True)
    show_winrate = BooleanProperty(True)

    score_points = ListProperty([])
    winrate_points = ListProperty([])

    score_dot_pos = ListProperty([0, 0])
    winrate_dot_pos = ListProperty([0, 0])
    highlight_size = NumericProperty(dp(6))

    score_scale = NumericProperty(5)
    winrate_scale = NumericProperty(5)

    navigate_move = ListProperty([None, 0, 0, 0])

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and "scroll" not in getattr(touch, "button", ""):
            ix, _ = min(enumerate(self.score_points[::2]), key=lambda ix_v: abs(ix_v[1] - touch.x))
            self.navigate_move = [
                self.nodes[ix],
                self.score_points[2 * ix],
                self.score_points[2 * ix + 1],
                self.winrate_points[2 * ix + 1],
            ]
        else:
            self.navigate_move = [None, 0, 0, 0]

    def on_touch_move(self, touch):
        return self.on_touch_down(touch)

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos) and self.navigate_move[0] and "scroll" not in getattr(touch, "button", ""):
            katrain = MDApp.get_running_app().gui
            if katrain and katrain.game:
                katrain.game.set_current_node(self.navigate_move[0])
                katrain.update_state()
        self.navigate_move = [None, 0, 0, 0]

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
                [self.x + i * xscale, self.y + self.height / 2 + available_height / 2 * (val / self.score_scale)]
                for i, val in enumerate(score_values)
            ]
            winrate_line_points = [
                [self.x + i * xscale, self.y + self.height / 2 + available_height / 2 * (val / self.winrate_scale)]
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
                        self.y
                        + self.height / 2
                        + available_height / 2 * ((score_nn_values or [0])[-1] / self.score_scale)
                    )
                self.score_dot_pos = score_dot_point
                if math.isnan(winrate_dot_point[1]):
                    winrate_dot_point[1] = (
                        self.y
                        + self.height / 2
                        + available_height / 2 * ((winrate_nn_values or [0])[-1] / self.winrate_scale)
                    )
                self.winrate_dot_pos = winrate_dot_point


Builder.load_string(
    """
#:import Theme katrain.gui.theme.Theme

<Graph>:
    background_color: Theme.BOX_BACKGROUND_COLOR
    marker_font_size: 0.1 * self.height
    canvas.before:
        Color:
            rgba: root.background_color
        Rectangle:
            size: self.size
            pos: self.pos
        Color:
            rgba: [1,1,1,1]
        Rectangle:
            pos: self.pos
            size: self.size
            source: root.background_image

<ScoreGraph>:
    canvas:
        Color:
            rgba: Theme.SCORE_COLOR
        Line:
            points: root.score_points if root.show_score else []
            width: dp(1.1)
        Color:
            rgba: Theme.WINRATE_COLOR
        Line:
            points: root.winrate_points if root.show_winrate else []
            width: dp(1.1)
        Color:
            rgba: [0.5,0.5,0.5,1] if root.navigate_move[0] else [0,0,0,0]
        Line:
            points: root.navigate_move[1], root.y, root.navigate_move[1], root.y+root.height
            width: 1
        Color:
            rgba: Theme.GRAPH_DOT_COLOR
        Ellipse:
            id: score_dot
            pos: [c - self.highlight_size / 2 for c in (self.score_dot_pos if not self.navigate_move[0] else [self.navigate_move[1],self.navigate_move[2]] ) ]
            size: (self.highlight_size,self.highlight_size) if root.show_score else (0.0001,0.0001)
        Color:
            rgba: Theme.GRAPH_DOT_COLOR
        Ellipse:
            id: winrate_dot
            pos: [c - self.highlight_size / 2 for c in (self.winrate_dot_pos if not self.navigate_move[0] else [self.navigate_move[1],self.navigate_move[3]] ) ]
            size: (self.highlight_size,self.highlight_size) if root.show_winrate else (0.0001,0.0001)
    # score ticks
    GraphMarkerLabel:
        font_size: root.marker_font_size
        color: Theme.SCORE_MARKER_COLOR
        pos: root.x + root.width - self.width-1, root.pos[1]+root.height - self.font_size - 1
        text: 'B+{}'.format(root.score_scale)
        opacity: int(root.show_score)
    GraphMarkerLabel:
        font_size: root.marker_font_size
        color: Theme.SCORE_MARKER_COLOR
        pos: root.x + root.width - self.width-1, root.y + root.height*0.5 - self.height/2 + 2
        text: i18n._('Jigo')
        opacity: int(root.show_score)
    GraphMarkerLabel:
        font_size: root.marker_font_size
        color: Theme.SCORE_MARKER_COLOR
        pos: root.x + root.width - self.width-1, root.pos[1]
        text: 'W+' + str(int(root.score_scale))
        opacity: int(root.show_score)
    # wr ticks
    GraphMarkerLabel:
        font_size: root.marker_font_size
        color: Theme.WINRATE_MARKER_COLOR
        pos: root.pos[0]+1,  root.pos[1] + root.height - self.font_size - 1
        text: "{}%".format(50 + root.winrate_scale)
        opacity: int(root.show_winrate)
    GraphMarkerLabel:
        font_size: root.marker_font_size
        color: Theme.WINRATE_MARKER_COLOR
        pos:root.pos[0]+1, root.pos[1]
        text: "{}%".format(50 - root.winrate_scale)
        opacity: int(root.show_winrate)
"""
)
