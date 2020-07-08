import math
import threading

from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, Clock, ListProperty, NumericProperty, StringProperty
from kivy.uix.widget import Widget
from kivymd.app import MDApp

from katrain.core.constants import OUTPUT_ERROR
from katrain.core.lang import rank_label


class Graph(Widget):
    marker_font_size = NumericProperty(0)
    background_image = StringProperty("img/graph_bg.png")
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
        if self.collide_point(*touch.pos):
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
        if self.collide_point(*touch.pos) and self.navigate_move[0]:
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
                [self.x + i * xscale, self.y + self.height / 2 + available_height / 2 * (val / self.score_scale),]
                for i, val in enumerate(score_values)
            ]
            winrate_line_points = [
                [self.x + i * xscale, self.y + self.height / 2 + available_height / 2 * (val / self.winrate_scale),]
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


def averagemod(data):
    sorteddata = sorted(data)
    lendata = len(data)
    return sum(sorteddata[int(lendata * 0.2) : int(lendata * 0.8) + 1]) / (
        (int(lendata * 0.8) + 1) - int(lendata * 0.2)
    )  # average without the best and worst 20% of ranks


def gauss(data):
    return math.exp(-1 * (data) ** 2)


class RankGraph(Graph):
    black_rank_points = ListProperty([])
    white_rank_points = ListProperty([])
    segment_length = NumericProperty(80)
    RANK_CAP = 5

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calculate_trigger = Clock.create_trigger(lambda *args: self.rank_game(), 0.25)
        self.rank_by_player = {}

    @staticmethod
    def calculate_rank_for_player(segment_stats, num_intersec, player):
        non_obvious_moves = [
            (nl, r, val)
            for nl, r, val, pl in segment_stats
            if nl is not None and val < (0.8 * (1 - (num_intersec - nl) / num_intersec * 0.5)) and pl == player
        ]
        if not non_obvious_moves:
            return None
        num_legal, rank, value = zip(*non_obvious_moves)
        rank = [min(r, nl * 0.09) for r, nl in zip(rank, num_legal)]
        averagemod_rank = averagemod(rank)
        averagemod_len_legal = averagemod(num_legal)
        norm_avemod_len_legal = averagemod_len_legal / num_intersec
        if averagemod_rank > 0.1:
            rank_kyu = (
                -0.97222
                * math.log(averagemod_rank)
                / (0.24634 + averagemod_rank * gauss(3.3208 * (norm_avemod_len_legal)))
                + 12.703 * (norm_avemod_len_legal)
                + 11.198 * math.log(averagemod_rank)
                + 12.28 * gauss(2.379 * (norm_avemod_len_legal))
                - 16.544
            )
        else:
            rank_kyu = -4
        return min(RankGraph.RANK_CAP, 1 - rank_kyu)  # dan rank

    @staticmethod
    def calculate_ranks(segment_stats, num_intersec):
        return {pl: RankGraph.calculate_rank_for_player(segment_stats, num_intersec, pl) for pl in "BW"}

    def rank_game(self):
        try:
            nodes = self.nodes
            parent_policy_per_move = [node.parent.policy_ranking if node.parent else None for node in nodes]
            num_legal_moves = [
                sum(pv >= 0 for pv, _ in policy_ranking) if policy_ranking else 0
                for policy_ranking in parent_policy_per_move
            ]
            policy_stats = [
                [
                    (num_mv, rank, value, mv.player)
                    for rank, (value, mv) in enumerate(policy_ranking)
                    if mv == node.move
                ][0]
                if policy_ranking and node.move
                else (None, None, None, None)
                for node, policy_ranking, num_mv in zip(nodes, parent_policy_per_move, num_legal_moves)
            ]
            size = self.nodes[0].board_size
            num_intersec = size[0] * size[1]
            half_seg = self.segment_length // 2

            ranks = {"B": [], "W": []}
            dx = self.segment_length // 4
            for segment_mid in range(dx, len(nodes), dx):
                bounds = (max(0, segment_mid - half_seg), min(segment_mid + half_seg, len(nodes)))
                num_analyzed = sum(num_mv is not None for num_mv, _, _, _ in policy_stats[bounds[0] : bounds[1] + 1])
                if num_analyzed >= self.segment_length * 0.75:
                    for pl, rank in self.calculate_ranks(policy_stats[bounds[0] : bounds[1] + 1], num_intersec).items():
                        ranks[pl].append((segment_mid, rank))
            self.rank_by_player = ranks
        except Exception as e:
            MDApp.get_running_app().gui.log(f"Exception while calculating rank: {e}", OUTPUT_ERROR)
        self.redraw_trigger()

    def update_value(self, node):
        super().update_value(node)
        self.trigger_calculate()

    def trigger_calculate(self):
        if self.opacity != 0:  # recalc here on trigger and only if visible for speed
            self.calculate_trigger()

    def update_graph(self, *args):
        if self.rank_by_player:
            xscale = self.width / max(len(self.nodes) - 1, 15)
            available_height = self.height

            all_ranks = [rank for lst in self.rank_by_player.values() for seg, rank in lst if rank is not None]
            if not all_ranks:
                return

            min_rank = math.floor(min(all_ranks))
            max_rank = math.ceil(max(all_ranks))
            if max_rank == min_rank:
                min_rank -= 1
            if (max_rank - min_rank) % 2 != 0:  # make midpoint whole integer
                if abs(max_rank - max(all_ranks)) < abs(min(all_ranks) - min_rank) and max_rank < self.RANK_CAP:
                    max_rank += 1
                else:
                    min_rank -= 1
            rank_range = max_rank - min_rank

            self.ids.mid_marker.text = rank_label((max_rank + min_rank) / 2)
            self.ids.top_marker.text = rank_label(max_rank) + ("+" if max_rank == self.RANK_CAP else "")
            self.ids.bottom_marker.text = rank_label(min_rank)

            graph_points = {}
            for pl, rank_points in self.rank_by_player.items():
                graph_points[pl] = [
                    [
                        self.x + i * xscale,
                        self.y + available_height * (val - min_rank) / rank_range if val is not None else math.nan,
                    ]
                    for i, val in rank_points
                ]
            self.black_rank_points = sum(graph_points["B"], [])
            self.white_rank_points = sum(graph_points["W"], [])
        else:
            self.black_rank_points = []
            self.white_rank_points = []


Builder.load_string(
    """
#:set GRAPH_CENTER_COLOR [0.5,0.5,0.5]
#:set GRAPH_DOT_COLOR [0.85,0.3,0.3,1]
#:set WINRATE_MARKER_COLOR [0.05, 0.7, 0.05, 1]
#:set SCORE_MARKER_COLOR [0.2, 0.6, 0.8, 1]

#:import LIGHTER_BACKGROUND_COLOR katrain.gui.style.LIGHTER_BACKGROUND_COLOR
#:import BOX_BACKGROUND_COLOR katrain.gui.style.BOX_BACKGROUND_COLOR
#:import SCORE_COLOR katrain.gui.style.SCORE_COLOR
#:import WINRATE_COLOR katrain.gui.style.WINRATE_COLOR
#:import BLACK katrain.gui.style.BLACK
#:import WHITE katrain.gui.style.WHITE
#:import YELLOW katrain.gui.style.YELLOW

<Graph>:
    background_color: BOX_BACKGROUND_COLOR
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
            rgba: SCORE_COLOR
        Line:
            points: root.score_points if root.show_score else []
            width: dp(1.1)
        Color:
            rgba: WINRATE_COLOR
        Line:
            points: root.winrate_points if root.show_winrate else []
            width: dp(1.1)
        Color:
            rgba: [0.5,0.5,0.5,1] if root.navigate_move[0] else [0,0,0,0]
        Line:
            points: root.navigate_move[1], root.y, root.navigate_move[1], root.y+root.height
            width: 1
        Color:
            rgba: GRAPH_DOT_COLOR
        Ellipse:
            id: score_dot
            pos: [c - self.highlight_size / 2 for c in (self.score_dot_pos if not self.navigate_move[0] else [self.navigate_move[1],self.navigate_move[2]] ) ]
            size: (self.highlight_size,self.highlight_size) if root.show_score else (0.0001,0.0001)
        Color:
            rgba: GRAPH_DOT_COLOR
        Ellipse:
            id: winrate_dot
            pos: [c - self.highlight_size / 2 for c in (self.winrate_dot_pos if not self.navigate_move[0] else [self.navigate_move[1],self.navigate_move[3]] ) ]
            size: (self.highlight_size,self.highlight_size) if root.show_winrate else (0.0001,0.0001)
    # score ticks
    GraphMarkerLabel:
        font_size: root.marker_font_size
        color: SCORE_MARKER_COLOR
        pos: root.x + root.width - self.width-1, root.pos[1]+root.height - self.font_size - 1
        text: 'B+{}'.format(root.score_scale)
        opacity: int(root.show_score)
    GraphMarkerLabel:
        font_size: root.marker_font_size
        color: SCORE_MARKER_COLOR
        pos: root.x + root.width - self.width-1, root.y + root.height*0.5 - self.height/2 + 2
        text: i18n._('Jigo')
        opacity: int(root.show_score)
    GraphMarkerLabel:
        font_size: root.marker_font_size
        color: SCORE_MARKER_COLOR
        pos: root.x + root.width - self.width-1, root.pos[1]
        text: 'W+' + str(int(root.score_scale))
        opacity: int(root.show_score)
    # wr ticks
    GraphMarkerLabel:
        font_size: root.marker_font_size
        color: WINRATE_MARKER_COLOR
        pos: root.pos[0]+1,  root.pos[1] + root.height - self.font_size - 1
        text: "{}%".format(50 + root.winrate_scale)
        opacity: int(root.show_winrate)
    GraphMarkerLabel:
        font_size: root.marker_font_size
        color: WINRATE_MARKER_COLOR
        pos:root.pos[0]+1, root.pos[1]
        text: "{}%".format(50 - root.winrate_scale)
        opacity: int(root.show_winrate) 

<RankGraph>:
    background_color: LIGHTER_BACKGROUND_COLOR
    canvas:
        Color:
            rgba: WHITE
        Line:
            points: root.white_rank_points
            width: dp(1.1)
        Color:
            rgba: BLACK
        Line:
            points: root.black_rank_points
            width: dp(1.1)
    # rank ticks
    GraphMarkerLabel:
        id: mid_marker
        font_size: root.marker_font_size
        color:  YELLOW
        pos: root.x + root.width - self.width-1, root.y + root.height*0.5 - self.height/2 + 2
        text: '?' + i18n._('strength:kyu')
    GraphMarkerLabel:
        id: top_marker
        font_size: root.marker_font_size
        color: YELLOW
        pos: root.x + root.width - self.width-1,  root.pos[1]+root.height - self.font_size - 1
        text: '?' + i18n._('strength:kyu')
    GraphMarkerLabel:
        id: bottom_marker
        font_size: root.marker_font_size
        color: YELLOW
        pos: root.x + root.width - self.width-1, root.pos[1]
        text: '?' + i18n._('strength:kyu')
"""
)
