from kivy.app import App
from kivy.graphics import *
from kivy.properties import NumericProperty, ObjectProperty
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.widget import Widget

import math

from controller import Config
from move import Move
from kivyutils import *

# (;GM[1]SZ[9]KM[7.5]RU[JP];B[fe];W[de];B[ec];W[dc];B[eg];W[dg];B[dh];W[ed];B[fd];W[ef];B[ff];W[eb];B[fc];W[eh];B[fg];W[ch];B[ee];W[df];B[dd];W[cd];B[db];W[cc];B[cb];W[fb];B[gb];W[bb];B[ea];W[ca];B[fa];W[fh];B[gh];W[ba];B[fi];W[di];B[da];W[ed];B[bc];W[bd];B[dd];W[ei];B[gi];W[ed])
# (;GM[1]SZ[19]KM[7.5]RU[JP];B[qd];W[pp];B[cd];W[cp];B[ec];W[od];B[oc];W[nc];B[pc];W[nd];B[qf];W[jc];B[eq];W[do];B[hq];W[jq];B[cr];W[qn];B[cj];W[cl];B[nq];W[oq];B[np];W[lp];B[cg];W[nn];B[lr];W[kq];B[mo];W[kn];B[qi];W[mn];B[hc];W[qk];B[lc];W[je];B[jb];W[kb];B[kc];W[ib];B[jd];W[ja];B[lb];W[id];B[kd];W[ic];B[oj];W[pd];B[qe];W[qc];B[qb];W[rc];B[rb];W[pb];B[ob];W[nb];B[pa];W[lf];B[la];W[ma];B[mj];W[nk];B[ge];W[hd];B[hg];W[fc];B[fb];W[gc];B[ed];W[og];B[of];W[nf];B[pg];W[fq];B[fp];W[er];B[fr];W[dq];B[gq];W[dr];B[eo];W[en];B[fn];W[fm];B[gn];W[gm];B[dn];W[em];B[co];W[dp];B[hn];W[ep];B[fq];W[fj];B[jo];W[jn];B[jr];W[kr];B[hr];W[fo];B[js];W[ks];B[iq];W[io];B[ng];W[mg];B[oh];W[ne];B[hm];W[hl];B[fg];W[ip];B[go];W[gs];B[fs];W[ok];B[mh];W[lh];B[li];W[hp];B[im];W[hs];B[il];W[ir];B[ke];W[kf];B[gp];W[bk];B[kl];W[bj];B[lo];W[ko];B[ll];W[ml];B[rj];W[rk];B[kh];W[ci];B[lg];W[if];B[hk];W[ei];B[gi];W[bg];B[bh];W[ch];B[bf];W[dg];B[cf];W[df];B[pj];W[pk];B[sk];W[sl];B[sj];W[rl];B[gb];W[hb];B[gl];W[fl];B[gj];W[de];B[bi];W[ai];B[ag];W[dd];B[dc];W[ce];B[be];W[cc];B[bd];W[qj];B[ri];W[eh];B[lm];W[ln];B[jg];W[jf];B[mf];W[me];B[ig];W[mk];B[lk];W[nj];B[ni];W[eo];B[mm];W[nm];B[fd];W[gd];B[hf];W[ga];B[ea];W[jm];B[jl];W[pe];B[fh];W[fi];B[es];W[ds];B[fk];W[ek];B[gk];W[mb];B[eg];W[oa];B[na];W[fe];B[he];W[oa];B[pb];W[ee];B[cb];W[ie];B[ff];W[dh];B[pf];W[mg];B[ej];W[dj];B[kg];W[mf];B[in];W[jp];B[na];W[aj];B[ah];W[oa];B[pq];W[or];B[na];W[ha];B[oa];W[fa];B[eb];W[];B[gr];W[is];B[oe];W[ho];B[km];W[ef])

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
        prevghost = self.ghost_stone
        if self.engine.ready and max(yd, xd) < self.grid_size / 2 and (xp, yp) not in [(x, y) for _, x, y in self.engine.stones]:
            self.ghost_stone = (xp, yp)
        else:
            self.ghost_stone = None
        if prevghost != self.ghost_stone:
            self.redraw()

    def on_touch_move(self, touch):  # on_motion on_touch_move
        return self.on_touch_down(touch)

    def on_touch_up(self, touch):
        if self.ghost_stone:
            self.engine.action("play", self.ghost_stone)
        self.ghost_stone = None
        self.redraw()

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
            self.grid_size = board.size[0] / (self.engine.boardsize - 1 + 1.5 * margin)
            self.stone_size = self.grid_size * Config.get("ui")["stone_size"]
            self.gridpos = [math.floor((margin + i) * self.grid_size + 0.5) for i in range(self.engine.boardsize)]

            line_color = Config.get("ui")["line_color"]
            Color(*line_color)
            lo, hi = self.gridpos[0], self.gridpos[-1]
            for i in range(self.engine.boardsize):
                Line(points=[(self.gridpos[i], lo), (self.gridpos[i], hi)])
                Line(points=[(lo, self.gridpos[i]), (hi, self.gridpos[i])])

            # star points
            star_point_pos = 3 if self.engine.boardsize <= 11 else 4
            starpt_size = self.grid_size * Config.get("ui")["starpoint_size"]
            for x in [star_point_pos - 1, self.engine.boardsize - star_point_pos, int(self.engine.boardsize / 2)]:
                for y in [star_point_pos - 1, self.engine.boardsize - star_point_pos, int(self.engine.boardsize / 2)]:
                    draw_circle((self.gridpos[x], self.gridpos[y]), starpt_size, line_color)

            # coordinates
            Color(0.25, 0.25, 0.25)
            for i in range(self.engine.boardsize):
                draw_text(pos=(self.gridpos[i], lo / 2), text=Move.GTP_COORD[i], font_size=self.grid_size / 1.5)
                draw_text(pos=(lo / 2, self.gridpos[i]), text=str(i + 1), font_size=self.grid_size / 1.5)

    def redraw(self):
        self.canvas.clear()
        with self.canvas:
            # stones
            moves = self.engine.board.moves
            last_move = self.engine.board.current_move
            eval_map = {m.coords: (m.evaluation, m.previous_temperature) for m in moves}
            eval_on = [self.engine.eval.active(0), self.engine.eval.active(1)]
            has_stone = {}
            for i, m in enumerate(self.engine.stones):
                has_stone[m.coords] = m.player
                eval, evalsize = eval_map.get(m.coords, (None, None))
                evalcol = self._eval_spectrum(eval) if eval_on[m.player] and eval else None
                inner = COLORS[1 - m.player] if (m == last_move) else None
                self.draw_stone(m.coords[0], m.coords[1], COLORS[m.player], inner, evalcol, evalsize)

            # ownership
            if self.engine.ownership.active and last_move.ownership:
                ownership = last_move.ownership
                rsz = self.grid_size * 0.2
                ix = 0
                cp = self.engine.current_player
                for y in range(self.engine.boardsize - 1, -1, -1):
                    for x in range(self.engine.boardsize):
                        ix_owner = cp if ownership[ix] > 0 else 1 - cp
                        if ix_owner != (has_stone.get((x, y), -1)):
                            Color(*COLORS[ix_owner], abs(ownership[ix]))
                            Rectangle(pos=(self.gridpos[x] - rsz / 2, self.gridpos[y] - rsz / 2), size=(rsz, rsz))
                        ix = ix + 1

            # undos
            undo_coords = set()
            alpha = Config.get("ui")["undo_alpha"]
            for m in self.engine.board.current_move.children:
                if m.evaluation and m.coords[0] is not None:
                    undo_coords.add(m.coords)
                    evalcol = (*self._eval_spectrum(m.evaluation), alpha)
                    self.draw_stone(m.coords[0], m.coords[1], (*COLORS[m.player][:3], alpha), Config.get("ui")["undo_circle_col"], evalcol, self.EVAL_BOUNDS[1])

            # hints
            if last_move.analysis and self.engine.hints.active(self.engine.current_player):
                for d in last_move.analysis:
                    move = Move(gtpcoords=d["move"], player=0)
                    c = [*self._eval_spectrum(d["evaluation"]), 0.5]
                    if move.coords[0] is not None and move.coords not in undo_coords:
                        self.draw_stone(move.coords[0], move.coords[1], c)

            # hover next move ghost stone
            if self.ghost_stone:
                self.draw_stone(*self.ghost_stone, (*COLORS[self.engine.current_player], GHOST_ALPHA))

            # pass circle
            passed = len(moves) > 1 and last_move.is_pass
            if passed:
                if len(moves) > 2 and moves[-2].is_pass:
                    text = "game\nend"
                else:
                    text = "pass"
                Color(0.45, 0.05, 0.45, 0.5)
                center = self.gridpos[int(self.engine.boardsize / 2)]
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
