import math

from kivy.graphics.context_instructions import Color
from kivy.graphics.vertex_instructions import Ellipse, Line, Rectangle
from kivy.properties import ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget

from constants import OUTPUT_DEBUG
from gui.kivyutils import draw_circle, draw_text
from game import Move


class BadukPanWidget(Widget):
    board_color = ListProperty([0.85, 0.68, 0.40])

    def __init__(self, **kwargs):
        super(BadukPanWidget, self).__init__(**kwargs)
        self.ui_config = {}
        self.trainer_config = {}
        self.ghost_stone = []
        self.gridpos_x = []
        self.gridpos_y = []
        self.grid_size = 0
        self.stone_size = 0
        self.last_eval = 0

    # stone placement functions
    def _find_closest(self, pos, gridpos):
        return sorted([(abs(p - pos), i) for i, p in enumerate(gridpos)])[0]

    def on_touch_down(self, touch):
        if not self.gridpos_x:
            return
        xd, xp = self._find_closest(touch.x, self.gridpos_x)
        yd, yp = self._find_closest(touch.y, self.gridpos_y)
        prev_ghost = self.ghost_stone
        if max(yd, xd) < self.grid_size / 2 and (xp, yp) not in [m.coords for m in self.katrain.game.stones]:
            self.ghost_stone = (xp, yp)
        else:
            self.ghost_stone = None
        if prev_ghost != self.ghost_stone:
            self.draw_board_contents()

    def on_touch_move(self, touch):  # on_motion on_touch_move
        return self.on_touch_down(touch)

    def on_touch_up(self, touch):
        if not self.gridpos_x:
            return
        katrain = self.katrain
        if self.ghost_stone:
            katrain("play", self.ghost_stone)
        else:
            xd, xp = self._find_closest(touch.x, self.gridpos_x)
            yd, yp = self._find_closest(touch.y, self.gridpos_y)

            nodes_here = [node for node in katrain.game.current_node.nodes_from_root if node.single_move and node.single_move.coords == (xp, yp)]
            if nodes_here and max(yd, xd) < self.grid_size / 2:  # load old comment
                katrain.log(f"\nAnalysis:\n{nodes_here[-1].analysis}", OUTPUT_DEBUG)
                katrain.log(f"\nParent Analysis:\n{nodes_here[-1].parent.analysis}", OUTPUT_DEBUG)
                if not katrain.controls.ai_lock.active:
                    katrain.controls.info.text = nodes_here[-1].comment(sgf=True)
                    katrain.controls.show_evaluation_stats(nodes_here[-1])

        self.ghost_stone = None
        self.draw_board_contents()  # remove ghost

    # drawing functions
    def on_size(self, *args):
        self.draw_board()
        self.draw_board_contents()

    def draw_stone(self, x, y, col, outline_col=None, innercol=None, evalcol=None, evalscale=1.0, scale=1.0):
        stone_size = self.stone_size * scale
        draw_circle((self.gridpos_x[x], self.gridpos_y[y]), stone_size, col)
        if outline_col:
            Color(*outline_col)
            Line(circle=(self.gridpos_x[x], self.gridpos_y[y], stone_size), width=0.05 * stone_size)
        if evalcol:
            evalsize = self.stone_size * evalscale * self.ui_config["eval_dot_max_size"]
            draw_circle((self.gridpos_x[x], self.gridpos_y[y]), evalsize, evalcol)
        #            highlight_col = [ ((1-c)*0.33+e)/1.33  for c,e in zip(col,evalcol) ]
        #            Color(*highlight_col[:3],0.5)
        #            Line(circle=(self.gridpos[x], self.gridpos[y], evalsize))

        if innercol:
            Color(*innercol)
            Line(circle=(self.gridpos_x[x], self.gridpos_y[y], stone_size * 0.45 / 0.85), width=0.125 * stone_size)  # 1.75

    def eval_color(self, points_lost):
        colors = self.ui_config["eval_colors"]
        thresholds = self.trainer_config["eval_thresholds"]
        i = 0
        while i < len(thresholds) and points_lost < thresholds[i]:
            i += 1
        return colors[min(i, len(colors) - 1)]

    def draw_board(self, *args):
        if not self.ui_config:
            return
        katrain = self.katrain
        board_size = katrain.game.board_size
        self.canvas.before.clear()
        with self.canvas.before:
            # board
            board_px_size = min(self.width, self.height)
            self.board_color = self.ui_config["board_color"]
            Rectangle(pos=self.pos, size=(self.width, self.height))
            # grid lines
            margin = 1.5
            self.grid_size = board_px_size / (board_size - 1 + 1.5 * margin)
            self.stone_size = self.grid_size * self.ui_config["stone_size"]
            self.gridpos_x = [self.pos[0] + math.floor((margin + i) * self.grid_size + 0.5) for i in range(board_size)]
            self.gridpos_y = [self.pos[1] + math.floor((margin + i) * self.grid_size + 0.5) for i in range(board_size)]

            line_color = self.ui_config["line_color"]
            Color(*line_color)
            for i in range(board_size):
                Line(points=[(self.gridpos_x[i], self.gridpos_y[0]), (self.gridpos_x[i], self.gridpos_y[-1])])
                Line(points=[(self.gridpos_x[0], self.gridpos_y[i]), (self.gridpos_x[-1], self.gridpos_y[i])])

            # star points
            star_point_pos = 3 if board_size <= 11 else 4
            starpt_size = self.grid_size * self.ui_config["starpoint_size"]
            for x in [star_point_pos - 1, board_size - star_point_pos, int(board_size / 2)]:
                for y in [star_point_pos - 1, board_size - star_point_pos, int(board_size / 2)]:
                    draw_circle((self.gridpos_x[x], self.gridpos_y[y]), starpt_size, line_color)

            # coordinates
            Color(0.25, 0.25, 0.25)
            coord_offset = self.grid_size * margin / 2
            for i in range(board_size):
                draw_text(pos=(self.gridpos_x[i], self.gridpos_y[0] - coord_offset), text=Move.GTP_COORD[i], font_size=self.grid_size / 1.5)
                draw_text(pos=(self.gridpos_x[0] - coord_offset, self.gridpos_y[i]), text=str(i + 1), font_size=self.grid_size / 1.5)

    def draw_board_contents(self, *args):
        if not self.ui_config:
            return
        stone_color = self.ui_config["stones"]
        outline_color = self.ui_config["outline"]
        ghost_alpha = self.ui_config["ghost_alpha"]
        katrain = self.katrain
        board_size = katrain.game.board_size

        self.canvas.clear()
        with self.canvas:
            # stones
            current_node = katrain.game.current_node
            next_player = katrain.game.next_player
            full_eval_on = katrain.controls.eval.active_map
            has_stone = {}
            drawn_stone = {}
            for m in katrain.game.stones:
                has_stone[m.coords] = m.player

            show_n_eval = self.trainer_config["eval_off_show_last"]
            nodes = katrain.game.current_node.nodes_from_root
            for i, node in enumerate(nodes[::-1]):  # reverse order!
                points_lost = node.points_lost
                evalsize = 1
                for m in node.move_with_placements:
                    if has_stone.get(m.coords) and not drawn_stone.get(m.coords):  # skip captures, last only for
                        move_eval_on = full_eval_on[m.player] or i < show_n_eval
                        evalcol = self.eval_color(points_lost) if move_eval_on and points_lost is not None else None
                        inner = stone_color[m.opponent] if i == 0 else None
                        drawn_stone[m.coords] = m.player
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
                            Rectangle(pos=(self.gridpos_x[x] - rsz / 2, self.gridpos_y[y] - rsz / 2), size=(rsz, rsz))
                        ix = ix + 1

            policy = current_node.policy
            if not policy and current_node.parent and current_node.parent.policy and 'ai' in katrain.controls.player_mode('B') and 'ai' in katrain.controls.player_mode('W'):
                policy = current_node.parent.policy  # in the case of AI self-play we allow the policy to be one step out of date
            pass_btn = katrain.board_controls.pass_btn
            pass_btn.canvas.after.clear()
            if katrain.controls.policy.active and policy and not katrain.controls.ownership.active:
                ix = 0
                best_move_policy = max(*policy)
                for y in range(board_size - 1, -1, -1):
                    for x in range(board_size):
                        if policy[ix] > 0:
                            polsize = math.sqrt(policy[ix])
                            policy_circle_color = (*self.ui_config["policy_color"], self.ui_config["ghost_alpha"] + self.ui_config["top_move_x_alpha"] * (policy[ix] == best_move_policy))
                            self.draw_stone(x, y, policy_circle_color, scale=polsize)
                        ix = ix + 1
                polsize = math.sqrt(policy[ix])
                with pass_btn.canvas.after:
                    draw_circle((pass_btn.pos[0] + pass_btn.width / 2, pass_btn.pos[1] + pass_btn.height / 2), polsize * pass_btn.height / 2, (1, 0, 0, 0.5))

            # children of current moves in undo / review
            undo_coords = set()
            alpha = self.ui_config["_child_alpha"]
            for child_node in current_node.children:
                points_lost = child_node.points_lost
                m = child_node.single_move
                if m and m.coords is not None:
                    undo_coords.add(m.coords)
                    evalcol = (*self.eval_color(points_lost), alpha) if points_lost is not None else None
                    scale = self.ui_config.get("_child_scale", 0.95)
                    self.draw_stone(m.coords[0], m.coords[1], (*stone_color[m.player][:3], alpha), None, None, evalcol, evalscale=scale, scale=scale)

            # hints
            if katrain.controls.hints.active(next_player):
                hint_moves = current_node.candidate_moves
                for i, d in enumerate(hint_moves):
                    move = Move.from_gtp(d["move"])
                    if move.coords is not None and move.coords not in undo_coords:
                        alpha, scale =  self.ui_config["ghost_alpha"], 1.0
                        if i == 0:
                            c[3] += self.ui_config["top_move_x_alpha"]
                        elif d["visits"] < 0.1 * hint_moves[0]["visits"]: # TODO: config?
                            scale = 0.8
                        self.draw_stone(move.coords[0], move.coords[1], [*self.eval_color(d["pointsLost"]),alpha], scale=scale)

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
                center = (self.pos[0] + self.width / 2, self.pos[1] + self.height / 2)
                size = min(self.width, self.height) * 0.22
                Ellipse(pos=(center[0] - size / 2, center[1] - size / 2), size=(size, size))
                Color(0.15, 0.15, 0.15)
                draw_text(pos=center, text=text, font_size=size * 0.25, halign="center", outline_color=[0.95, 0.95, 0.95])


class BadukPanControls(BoxLayout):
    pass
