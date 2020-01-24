from kivy.app import App
from kivy.graphics import *
from kivy.properties import NumericProperty, ObjectProperty
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.widget import Widget

import math

from controller import Config
from board import Move
from kivyutils import *

COLORS = Config.get("ui")["stones"]
GHOST_ALPHA = Config.get("ui")["ghost_alpha"]


class BadukPanWidget(Widget):
    def __init__(self, **kwargs):
        super(BadukPanWidget, self).__init__(**kwargs)
        self.ghost_stone = []
        self.gridpos = []
        self.grid_size = 0
        self.stone_size = 0
        self.last_eval = 0
        self.EVAL_COLORS = Config.get("ui")["eval_colors"]
        self.EVAL_KNOTS = Config.get("ui")["eval_knots"]
        self.EVAL_BOUNDS = Config.get("ui")["eval_bounds"]

    # stone placement functions
    def _find_closest(self, pos):
        return sorted([(abs(p - pos), i) for i, p in enumerate(self.gridpos)])[0]

    def on_touch_down(self, touch):
        xd, xp = self._find_closest(touch.x)
        yd, yp = self._find_closest(touch.y)
        prev_ghost = self.ghost_stone
        if self.engine.ready and max(yd, xd) < self.grid_size / 2 and (xp, yp) not in [m.coords for m in self.engine.board.stones]:
            self.ghost_stone = (xp, yp)
        else:
            self.ghost_stone = None
        if prev_ghost != self.ghost_stone:
            self.redraw()

    def on_touch_move(self, touch):  # on_motion on_touch_move
        return self.on_touch_down(touch)

    def on_touch_up(self, touch):
        if self.ghost_stone:
            self.engine.action("play", self.ghost_stone)
        self.ghost_stone = None
        self.redraw() # remove ghost

    # drawing functions
    def on_size(self, *args):
        self.draw_board()
        self.redraw()

    def draw_stone(self, x, y, col, innercol=None, evalcol=None, evalsize=10.0):
        draw_circle((self.gridpos[x], self.gridpos[y]), self.stone_size, col)
        if evalcol:
            evalsize = min(self.EVAL_BOUNDS[1], max(evalsize, self.EVAL_BOUNDS[0])) / self.EVAL_BOUNDS[1]
            draw_circle((self.gridpos[x], self.gridpos[y]), math.sqrt(evalsize) * self.stone_size * 0.5, evalcol)
        if innercol:
            Color(*innercol)
            Line(circle=(self.gridpos[x], self.gridpos[y], self.stone_size * 0.45 / 0.85), width=1.75)

    def _eval_spectrum(self, score):
        score = max(0, score)
        for i in range(len(self.EVAL_KNOTS) - 1):
            if self.EVAL_KNOTS[i] <= score < self.EVAL_KNOTS[i + 1]:
                t = (score - self.EVAL_KNOTS[i]) / (self.EVAL_KNOTS[i + 1] - self.EVAL_KNOTS[i])
                return [a + t * (b - a) for a, b in zip(self.EVAL_COLORS[i], self.EVAL_COLORS[i + 1])]
        return self.EVAL_COLORS[-1]

    def draw_board(self):
        self.canvas.before.clear()
        with self.canvas.before:
            # board
            sz = self.height
            Color(*Config.get("ui")["board_color"])
            board = Rectangle(pos=(0, 0), size=(sz, sz))

            # grid lines
            margin = Config.get("ui")["board_margin"]
            self.grid_size = board.size[0] / (self.engine.board_size - 1 + 1.5 * margin)
            self.stone_size = self.grid_size * Config.get("ui")["stone_size"]
            self.gridpos = [math.floor((margin + i) * self.grid_size + 0.5) for i in range(self.engine.board_size)]

            line_color = Config.get("ui")["line_color"]
            Color(*line_color)
            lo, hi = self.gridpos[0], self.gridpos[-1]
            for i in range(self.engine.board_size):
                Line(points=[(self.gridpos[i], lo), (self.gridpos[i], hi)])
                Line(points=[(lo, self.gridpos[i]), (hi, self.gridpos[i])])

            # star points
            star_point_pos = 3 if self.engine.board_size <= 11 else 4
            starpt_size = self.grid_size * Config.get("ui")["starpoint_size"]
            for x in [star_point_pos - 1, self.engine.board_size - star_point_pos, int(self.engine.board_size / 2)]:
                for y in [star_point_pos - 1, self.engine.board_size - star_point_pos, int(self.engine.board_size / 2)]:
                    draw_circle((self.gridpos[x], self.gridpos[y]), starpt_size, line_color)

            # coordinates
            Color(0.25, 0.25, 0.25)
            for i in range(self.engine.board_size):
                draw_text(pos=(self.gridpos[i], lo / 2), text=Move.GTP_COORD[i], font_size=self.grid_size / 1.5)
                draw_text(pos=(lo / 2, self.gridpos[i]), text=str(i + 1), font_size=self.grid_size / 1.5)

    def redraw(self):
        self.canvas.clear()
        with self.canvas:
            # stones
            moves = self.engine.board.moves
            last_move = moves[-1] if moves else self.engine.board.root
            current_player = self.engine.board.current_player
            eval_on = [self.engine.eval.active(0), self.engine.eval.active(1)]
            has_stone = {}
            for i, m in enumerate(self.engine.board.stones):
                has_stone[m.coords] = m.player
                eval, evalsize = m.evaluation_info
                evalcol = self._eval_spectrum(eval) if eval_on[m.player] and eval else None
                inner = COLORS[1 - m.player] if (m == last_move) else None
                self.draw_stone(m.coords[0], m.coords[1], COLORS[m.player], inner, evalcol, evalsize)

            # ownership
            if self.engine.ownership.active and last_move.ownership:
                ownership = last_move.ownership
                rsz = self.grid_size * 0.2
                ix = 0
                for y in range(self.engine.board_size - 1, -1, -1):
                    for x in range(self.engine.board_size):
                        ix_owner = current_player if ownership[ix] > 0 else 1 - current_player
                        if ix_owner != (has_stone.get((x, y), -1)):
                            Color(*COLORS[ix_owner], abs(ownership[ix]))
                            Rectangle(pos=(self.gridpos[x] - rsz / 2, self.gridpos[y] - rsz / 2), size=(rsz, rsz))
                        ix = ix + 1

            # undos
            undo_coords = set()
            alpha = Config.get("ui")["undo_alpha"]
            for m in last_move.children:
                if m.evaluation and m.coords[0] is not None:
                    undo_coords.add(m.coords)
                    evalcol = (*self._eval_spectrum(m.evaluation), alpha)
                    self.draw_stone(m.coords[0], m.coords[1], (*COLORS[m.player][:3], alpha), Config.get("ui")["undo_circle_col"], evalcol, self.EVAL_BOUNDS[1])

            # hints
            if self.engine.hints.active(current_player):
                for d in last_move.ai_moves:
                    move = Move(gtpcoords=d["move"], player=0)
                    c = [*self._eval_spectrum(d["evaluation"]), 0.5]
                    if move.coords[0] is not None and move.coords not in undo_coords:
                        self.draw_stone(move.coords[0], move.coords[1], c)

            # hover next move ghost stone
            if self.ghost_stone:
                self.draw_stone(*self.ghost_stone, (*COLORS[current_player], GHOST_ALPHA))

            # pass circle
            passed = len(moves) > 1 and last_move.is_pass
            if passed:
                if len(moves) > 2 and moves[-2].is_pass:
                    text = "game\nend"
                else:
                    text = "pass"
                Color(0.45, 0.05, 0.45, 0.5)
                center = self.gridpos[int(self.engine.board_size / 2)]
                Ellipse(pos=(center - self.grid_size * 1.5, center - self.grid_size * 1.5), size=(self.grid_size * 3, self.grid_size * 3))
                Color(0.15, 0.15, 0.15)
                draw_text(pos=(center, center), text=text, font_size=self.grid_size * 0.66, halign="center", outline_color=[0.95, 0.95, 0.95])


class KaTrainGui(FloatLayout):
    pass


class KaTrainApp(App):
    def build(self):
        self.icon = "./icon.png"
        self.gui = KaTrainGui()
        return self.gui

    def on_start(self):
        self.gui.controls.restart()


if __name__ == "__main__":
    KaTrainApp().run()
