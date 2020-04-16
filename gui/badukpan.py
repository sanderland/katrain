import math

from kivy.graphics.context_instructions import Color
from kivy.graphics.vertex_instructions import Ellipse, Line, Rectangle
from kivy.uix.widget import Widget

from constants import OUTPUT_DEBUG
from gui.kivyutils import draw_circle, draw_text
from sgf_parser import Move


class BadukPanWidget(Widget):
    def __init__(self, **kwargs):
        super(BadukPanWidget, self).__init__(**kwargs)
        self.config = {}
        self.ghost_stone = []
        self.gridpos = []
        self.grid_size = 0
        self.stone_size = 0
        self.last_eval = 0

    # stone placement functions
    def _find_closest(self, pos):
        return sorted([(abs(p - pos), i) for i, p in enumerate(self.gridpos)])[0]

    def on_touch_down(self, touch):
        if not self.gridpos:
            return
        xd, xp = self._find_closest(touch.x)
        yd, yp = self._find_closest(touch.y)
        prev_ghost = self.ghost_stone
        if max(yd, xd) < self.grid_size / 2 and (xp, yp) not in [m.coords for m in self.parent.game.stones]:
            self.ghost_stone = (xp, yp)
        else:
            self.ghost_stone = None
        if prev_ghost != self.ghost_stone:
            self.draw_board_contents()

    def on_touch_move(self, touch):  # on_motion on_touch_move
        return self.on_touch_down(touch)

    def on_touch_up(self, touch):
        if not self.gridpos:
            return
        katrain = self.parent
        if self.ghost_stone:
            katrain("play", self.ghost_stone)
        else:
            xd, xp = self._find_closest(touch.x)
            yd, yp = self._find_closest(touch.y)

            nodes_here = [node for node in katrain.game.current_node.nodes_from_root if node.single_move and node.single_move.coords == (xp, yp)]
            if nodes_here and max(yd, xd) < self.grid_size / 2:  # load old comment
                katrain.log(f"\nAnalysis:\n{nodes_here[-1].analysis}", OUTPUT_DEBUG)
                katrain.log(f"\nParent Analysis:\n{nodes_here[-1].parent.analysis}", OUTPUT_DEBUG)
                if not katrain.controls.ai_lock.active:
                    katrain.controls.info.text = nodes_here[-1].comment(sgf=True)
                    katrain.show_evaluation_stats(nodes_here[-1])

        self.ghost_stone = None
        self.draw_board_contents()  # remove ghost

    # drawing functions
    def on_size(self, *args):
        self.draw_board()
        self.draw_board_contents()

    def draw_stone(self, x, y, col, outline_col=None, innercol=None, evalcol=None, evalscale=1.0, scale=1.0):
        stone_size = self.stone_size * scale
        draw_circle((self.gridpos[x], self.gridpos[y]), stone_size, col)
        if outline_col:
            Color(*outline_col)
            Line(circle=(self.gridpos[x], self.gridpos[y], stone_size), width=0.05 * stone_size)
        if evalcol:
            evalsize = self.stone_size * evalscale * self.config['eval_dot_max_size']
            draw_circle((self.gridpos[x], self.gridpos[y]), evalsize, evalcol)
#            highlight_col = [ ((1-c)*0.33+e)/1.33  for c,e in zip(col,evalcol) ]
#            Color(*highlight_col[:3],0.5)
#            Line(circle=(self.gridpos[x], self.gridpos[y], evalsize))

        if innercol:
            Color(*innercol)
            Line(circle=(self.gridpos[x], self.gridpos[y], stone_size * 0.45 / 0.85), width=0.125 * stone_size)  # 1.75

    def eval_color(self, points_lost):
        colors = self.config["eval_colors"]
        thresholds = self.config["eval_thresholds"]
        i = 0
        while i < len(thresholds) and points_lost < thresholds[i]:
            i += 1
        return colors[min(i,len(colors)-1)]

    def draw_board(self, *args):
        if not self.config:
            return
        katrain = self.parent
        board_size = katrain.game.board_size
        self.canvas.before.clear()
        with self.canvas.before:
            # board
            sz = min(self.width, self.height)
            Color(*self.config["board_color"])
            board_rectangle = Rectangle(pos=(0, 0), size=(sz, sz))
            # grid lines
            margin = self.config["board_margin"]
            self.grid_size = board_rectangle.size[0] / (board_size - 1 + 1.5 * margin)
            self.stone_size = self.grid_size * self.config["stone_size"]
            self.gridpos = [math.floor((margin + i) * self.grid_size + 0.5) for i in range(board_size)]

            line_color = self.config["line_color"]
            Color(*line_color)
            lo, hi = self.gridpos[0], self.gridpos[-1]
            for i in range(board_size):
                Line(points=[(self.gridpos[i], lo), (self.gridpos[i], hi)])
                Line(points=[(lo, self.gridpos[i]), (hi, self.gridpos[i])])

            # star points
            star_point_pos = 3 if board_size <= 11 else 4
            starpt_size = self.grid_size * self.config["starpoint_size"]
            for x in [star_point_pos - 1, board_size - star_point_pos, int(board_size / 2)]:
                for y in [star_point_pos - 1, board_size - star_point_pos, int(board_size / 2)]:
                    draw_circle((self.gridpos[x], self.gridpos[y]), starpt_size, line_color)

            # coordinates
            Color(0.25, 0.25, 0.25)
            for i in range(board_size):
                draw_text(pos=(self.gridpos[i], lo / 2), text=Move.GTP_COORD[i], font_size=self.grid_size / 1.5)
                draw_text(pos=(lo / 2, self.gridpos[i]), text=str(i + 1), font_size=self.grid_size / 1.5)

    def draw_board_contents(self, *args):
        if not self.config:
            return
        stone_color = self.config["stones"]
        outline_color = self.config["outline"]
        ghost_alpha = self.config["ghost_alpha"]
        katrain = self.parent
        board_size = katrain.game.board_size

        self.canvas.clear()
        with self.canvas:
            # stones
            current_node = katrain.game.current_node
            next_player = katrain.game.next_player
            full_eval_on = {p: katrain.controls.eval.active(p) for p in Move.PLAYERS}  # TODO: map? TODO: settings here
            has_stone = {}
            for m in katrain.game.stones:
                has_stone[m.coords] = m.player

            show_n_eval = self.config["eval_off_show_last"]
            nodes = katrain.game.current_node.nodes_from_root
            for i, node in enumerate(nodes):
                eval = node.points_lost
                evalsize = 1
                for m in node.move_with_placements:
                    if has_stone[m.coords]:  # skip captures, draw over repeat plays
                        move_eval_on = full_eval_on[m.player] or i >= len(nodes) - show_n_eval
                        evalcol = self.eval_color(eval) if move_eval_on and eval and evalsize > self.config.get("min_eval_temperature", 0.5) else None
                        inner = stone_color[m.opponent] if (m is current_node) else None
                        self.draw_stone(m.coords[0], m.coords[1], stone_color[m.player], outline_color[m.player], inner, evalcol, evalsize)

            # ownership - allow one move out of date for smooth animation
            ownership = current_node.ownership or (current_node.parent and current_node.parent.ownership)
            if katrain.controls.ownership.active and ownership:
                rsz = self.grid_size * 0.2
                ix = 0
                for y in range(board_size - 1, -1, -1):
                    for x in range(board_size):
                        ix_owner = "B" if ownership[ix] > 0 else "W"
                        if ix_owner != (has_stone.get((x, y), -1)):
                            Color(*stone_color[ix_owner], abs(ownership[ix]))
                            Rectangle(pos=(self.gridpos[x] - rsz / 2, self.gridpos[y] - rsz / 2), size=(rsz, rsz))
                        ix = ix + 1

            # children of current moves in undo / review
            undo_coords = set()
            alpha = self.config["undo_alpha"]
            for child_node in current_node.children:
                points_lost = node.points_lost
                m = child_node.single_move
                if m and m.coords[0] is not None:
                    undo_coords.add(m.coords)
                    evalcol = (*self.eval_color(points_lost), alpha) if points_lost else None
                    scale = self.config.get("undo_scale", 0.95)
                    self.draw_stone(m.coords[0], m.coords[1], (*stone_color[m.player][:3], alpha), None, None, evalcol, evalscale=scale, scale=scale)

            # hints
            if katrain.controls.hints.active(next_player):
                hint_moves = current_node.ai_moves
                for i, d in enumerate(hint_moves):
                    move = Move.from_gtp(d["move"])
                    c = [*self.eval_color(d["evaluation"]), 0.5]
                    if move.coords[0] is not None and move.coords not in undo_coords:
                        if i == 0:
                            scale = 1.0
                        elif d["visits"] < 0.1 * hint_moves[0]["visits"]:  # TODO: config?
                            scale = 0.6  # TODO: config?
                        else:
                            scale = 0.85
                        self.draw_stone(move.coords[0], move.coords[1], c, scale=scale)

            # hover next move ghost stone
            if self.ghost_stone:
                self.draw_stone(*self.ghost_stone, (*stone_color[next_player], ghost_alpha))

            # pass circle
            passed = len(nodes) > 1 and current_node.is_pass
            if passed:
                if katrain.game.game_ended:
                    text = "game\nend"
                else:
                    text = "pass"
                Color(0.45, 0.05, 0.45, 0.5)
                center = self.gridpos[int(board_size / 2)]
                Ellipse(pos=(center - self.grid_size * 1.5, center - self.grid_size * 1.5), size=(self.grid_size * 3, self.grid_size * 3))
                Color(0.15, 0.15, 0.15)
                draw_text(pos=(center, center), text=text, font_size=self.grid_size * 0.66, halign="center", outline_color=[0.95, 0.95, 0.95])
