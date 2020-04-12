import math
import signal

from kivy.app import App
from kivy.core.window import Window
from kivy.graphics import *
from kivy.uix.widget import Widget

from board import Move
from controller import Config
from kivyutils import *

STONE_COLORS = Config.get("ui")["stones"]
OUTLINE_COLORS = Config.get("ui").get("outline", [None, None])
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
        else:
            xd, xp = self._find_closest(touch.x)
            yd, yp = self._find_closest(touch.y)
            stones_here = [m for m in self.engine.board.stones if m.coords == (xp, yp)]
            if stones_here and max(yd, xd) < self.grid_size / 2:  # load old comment
                if self.engine.debug:
                    print("\nAnalysis:\n", stones_here[-1].analysis)
                    print("\nParent Analysis:\n", stones_here[-1].parent.analysis)
                    if stones_here[-1].parent.pass_analysis:
                        print("\nParent Pass Analysis:\n", stones_here[-1].parent.pass_analysis[0])
                if not self.engine.ai_lock.active:
                    self.engine.info.text = stones_here[-1].comment(sgf=True)
                    self.engine.show_evaluation_stats(stones_here[-1])

        self.ghost_stone = None
        self.redraw()  # remove ghost

    # drawing functions
    def on_size(self, *args):
        self.draw_board()
        self.redraw()

    def draw_stone(self, x, y, col, outline_col=None, innercol=None, evalcol=None, evalsize=10.0, scale=1.0):
        stone_size = self.stone_size * scale
        draw_circle((self.gridpos[x], self.gridpos[y]), stone_size, col)
        if outline_col:
            Color(*outline_col)
            Line(circle=(self.gridpos[x], self.gridpos[y], stone_size), width=0.05 * stone_size)

        if evalcol:
            evalsize = min(self.EVAL_BOUNDS[1], max(evalsize, self.EVAL_BOUNDS[0])) / self.EVAL_BOUNDS[1]
            draw_circle((self.gridpos[x], self.gridpos[y]), math.sqrt(evalsize) * stone_size * 0.5, evalcol)
        if innercol:
            Color(*innercol)
            Line(circle=(self.gridpos[x], self.gridpos[y], stone_size * 0.45 / 0.85), width=0.125 * stone_size)  # 1.75

    def _eval_spectrum(self, score):
        score = max(0, score)
        for i in range(len(self.EVAL_KNOTS) - 1):
            if self.EVAL_KNOTS[i] <= score < self.EVAL_KNOTS[i + 1]:
                t = (score - self.EVAL_KNOTS[i]) / (self.EVAL_KNOTS[i + 1] - self.EVAL_KNOTS[i])
                return [a + t * (b - a) for a, b in zip(self.EVAL_COLORS[i], self.EVAL_COLORS[i + 1])]
        return self.EVAL_COLORS[-1]

    def draw_board(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            # board
            sz = min(self.width, self.height)
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

    def redraw(self, *args):
        self.canvas.clear()
        with self.canvas:
            # stones
            moves = self.engine.board.moves
            last_move = moves[-1] if moves else self.engine.board.root
            current_player = self.engine.board.current_player
            full_eval_on = [self.engine.eval.active(0), self.engine.eval.active(1)]
            has_stone = {}
            last_few_moves = self.engine.board.moves[-Config.get("trainer").get("eval_off_show_last", 3) :]
            for i, m in enumerate(self.engine.board.stones):
                has_stone[m.coords] = m.player
                eval, evalsize = m.evaluation_info
                move_eval_on = full_eval_on[m.player] or m in last_few_moves
                evalcol = self._eval_spectrum(eval) if move_eval_on and eval and evalsize > Config.get("ui").get("min_eval_temperature", 0.5) else None
                inner = STONE_COLORS[1 - m.player] if (m == last_move) else None
                self.draw_stone(m.coords[0], m.coords[1], STONE_COLORS[m.player], OUTLINE_COLORS[m.player], inner, evalcol, evalsize)

            # ownership - allow one move out of date for smooth animation
            ownership = last_move.ownership or (last_move.parent and last_move.parent.ownership)
            if self.engine.ownership.active and ownership:
                rsz = self.grid_size * 0.2
                ix = 0
                for y in range(self.engine.board_size - 1, -1, -1):
                    for x in range(self.engine.board_size):
                        ix_owner = 0 if ownership[ix] > 0 else 1
                        if ix_owner != (has_stone.get((x, y), -1)):
                            Color(*STONE_COLORS[ix_owner], abs(ownership[ix]))
                            Rectangle(pos=(self.gridpos[x] - rsz / 2, self.gridpos[y] - rsz / 2), size=(rsz, rsz))
                        ix = ix + 1

            policy = last_move.policy
            if self.engine.policy.active and policy:
                best_move_policy = max(policy)
                print(sorted(policy))
                rsz = self.grid_size * 0.2
                ix = 0
                for y in range(self.engine.board_size - 1, -1, -1):
                    for x in range(self.engine.board_size):
                        if policy[ix] > 0:
                            polcol = self._eval_spectrum((policy[ix] / best_move_policy) ** 0.1)
                            Color(*polcol)
                            Rectangle(pos=(self.gridpos[x] - rsz / 2, self.gridpos[y] - rsz / 2), size=(rsz, rsz))
                        ix = ix + 1

            # children of current moves in undo / review
            undo_coords = set()
            alpha = Config.get("ui")["undo_alpha"]
            for m in last_move.children:
                eval_info = m.evaluation_info
                if m.coords[0] is not None:
                    undo_coords.add(m.coords)
                    evalcol = (*self._eval_spectrum(eval_info[0]), alpha) if eval_info[0] else None
                    scale = Config.get("ui").get("undo_scale", 0.95)
                    self.draw_stone(m.coords[0], m.coords[1], (*STONE_COLORS[m.player][:3], alpha), None, None, evalcol, self.EVAL_BOUNDS[1], scale=scale)

            # hints
            if self.engine.hints.active(current_player):
                for i, d in enumerate(last_move.ai_moves):
                    move = Move(gtpcoords=d["move"], player=0)
                    c = [*self._eval_spectrum(d["evaluation"]), 0.5]
                    if move.coords[0] is not None and move.coords not in undo_coords:
                        self.draw_stone(move.coords[0], move.coords[1], c, scale=1.0 if i == 0 else 0.8)

            # hover next move ghost stone
            if self.ghost_stone:
                self.draw_stone(*self.ghost_stone, (*STONE_COLORS[current_player], GHOST_ALPHA))

            # pass circle
            passed = len(moves) > 1 and last_move.is_pass
            if passed:
                if self.engine.board.game_ended:
                    text = "game\nend"
                else:
                    text = "pass"
                Color(0.45, 0.05, 0.45, 0.5)
                center = self.gridpos[int(self.engine.board_size / 2)]
                Ellipse(pos=(center - self.grid_size * 1.5, center - self.grid_size * 1.5), size=(self.grid_size * 3, self.grid_size * 3))
                Color(0.15, 0.15, 0.15)
                draw_text(pos=(center, center), text=text, font_size=self.grid_size * 0.66, halign="center", outline_color=[0.95, 0.95, 0.95])


class KaTrainGui(BoxLayout):
    def __init__(self, **kwargs):
        super(KaTrainGui, self).__init__(**kwargs)
        self._keyboard = Window.request_keyboard(None, self, "")
        self._keyboard.bind(on_key_down=self._on_keyboard_down)

    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        if keycode[1] == "up":
            self.controls.action("undo")
        elif keycode[1] == "down":
            self.controls.action("redo")
        elif keycode[1] == "right":
            self.controls.action("redo-branch", 1)
        elif keycode[1] == "left":
            self.controls.action("redo-branch", -1)
        return True


class KaTrainApp(App):
    def build(self):
        self.icon = "./icon.png"
        self.gui = KaTrainGui()
        return self.gui

    def on_start(self):
        self.gui.controls.restart()
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, signal, frame):
        import sys
        import traceback

        if self.gui.controls.debug:
            code = ["TRACEBACKS"]
            for threadId, stack in sys._current_frames().items():
                code.append("\n# ThreadID: %s" % threadId)
                for filename, lineno, name, line in traceback.extract_stack(stack):
                    code.append('File: "%s", line %d, in %s' % (filename, lineno, name))
                    if line:
                        code.append("  %s" % (line.strip()))
            print("\n".join(code))
        sys.exit(0)


if __name__ == "__main__":
    KaTrainApp().run()
