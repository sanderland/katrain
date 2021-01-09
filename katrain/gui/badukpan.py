import math
import random
import time
from typing import List, Optional

from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.window import Window
from kivy.graphics.context_instructions import Color
from kivy.graphics.vertex_instructions import Ellipse, Line, Rectangle
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, ObjectProperty
from kivy.uix.dropdown import DropDown
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout

from katrain.core.constants import (
    MODE_PLAY,
    OUTPUT_DEBUG,
    OUTPUT_EXTRA_DEBUG,
    STATUS_TEACHING,
    TOP_MOVE_DELTA_SCORE,
    TOP_MOVE_DELTA_WINRATE,
    TOP_MOVE_NOTHING,
    TOP_MOVE_OPTIONS,
    TOP_MOVE_SCORE,
    TOP_MOVE_VISITS,
    TOP_MOVE_WINRATE,
)
from katrain.core.game import Move
from katrain.core.lang import i18n
from katrain.core.utils import evaluation_class, format_visits, var_to_grid, json_truncate_arrays
from katrain.gui.kivyutils import draw_circle, draw_text, cached_texture
from katrain.gui.popups import I18NPopup, ReAnalyzeGamePopup
from katrain.gui.theme import Theme


class BadukPanWidget(Widget):
    def __init__(self, **kwargs):
        super(BadukPanWidget, self).__init__(**kwargs)
        self.stones_sounds = [SoundLoader.load(file) for file in Theme.STONE_SOUNDS]
        self.trainer_config = {}
        self.ghost_stone = []
        self.gridpos_x = []
        self.gridpos_y = []
        self.grid_size = 0
        self.stone_size = 0
        self.selecting_region_of_interest = False
        self.region_of_interest = []
        self.draw_coords_enabled = True

        self.active_pv_moves = []
        self.animating_pv = None
        self.last_mouse_pos = (0, 0)
        Window.bind(mouse_pos=self.on_mouse_pos)
        self.redraw_board_contents_trigger = Clock.create_trigger(self.draw_board_contents, 0.05)
        self.redraw_trigger = Clock.create_trigger(self.redraw, 0.05)
        self.redraw_hover_contents_trigger = Clock.create_trigger(self.draw_hover_contents, 0.01)
        self.bind(size=self.redraw_trigger, pos=self.redraw_trigger)
        Clock.schedule_interval(self.animate_pv, 0.1)

    def toggle_coordinates(self):
        self.draw_coords_enabled = not self.draw_coords_enabled
        self.redraw_trigger()
        return self.draw_coords_enabled

    def get_enable_coordinates(self):
        return self.draw_coords_enabled

    def play_stone_sound(self, *_args):
        if self.katrain.config("timer/sound"):
            sound = random.choice(self.stones_sounds)
            if sound:
                sound.play()

    # stone placement functions
    def _find_closest(self, pos, gridpos):
        return sorted([(abs(p - pos), i) for i, p in enumerate(gridpos)])[0]

    def check_next_move_ghost(self, touch):
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
            self.redraw_hover_contents_trigger()

    def update_box_selection(self, touch, second_point=True):
        if not self.gridpos_x:
            return
        _, xp = self._find_closest(touch.x, self.gridpos_x)
        _, yp = self._find_closest(touch.y, self.gridpos_y)
        if second_point and len(self.region_of_interest) == 4:
            self.region_of_interest[1] = xp
            self.region_of_interest[3] = yp
        else:
            self.region_of_interest = [xp, xp, yp, yp]
        self.redraw_hover_contents_trigger()

    def on_touch_down(self, touch):
        self.set_animating_pv(None, None)  # any click kills PV from label/move
        if "button" in touch.profile and touch.button != "left":
            return
        if self.selecting_region_of_interest:
            self.update_box_selection(touch, second_point=False)
        else:
            self.check_next_move_ghost(touch)

    def on_touch_move(self, touch):
        if "button" in touch.profile and touch.button != "left":
            return
        if self.selecting_region_of_interest:
            return self.update_box_selection(touch)
        else:
            return self.check_next_move_ghost(touch)

    def on_mouse_pos(self, *args):  # https://gist.github.com/opqopq/15c707dc4cffc2b6455f
        if self.get_root_window():  # don't proceed if I'm not displayed <=> If have no parent
            pos = args[1]
            rel_pos = self.to_widget(*pos)  # compensate for relative layout
            inside = self.collide_point(*rel_pos)

            if inside and self.active_pv_moves and not self.selecting_region_of_interest:
                near_move = [
                    (pv, node)
                    for move, pv, node in self.active_pv_moves
                    if move[0] < len(self.gridpos_x)
                    and move[1] < len(self.gridpos_y)
                    and abs(rel_pos[0] - self.gridpos_x[move[0]]) < self.grid_size / 2
                    and abs(rel_pos[1] - self.gridpos_y[move[1]]) < self.grid_size / 2
                ]
                if near_move:
                    self.set_animating_pv(near_move[0][0], near_move[0][1])
                elif self.animating_pv is not None:
                    self.set_animating_pv(None, None)  # any click kills PV from label/move
            if inside and self.animating_pv is not None:
                d_sq = (pos[0] - self.animating_pv[3][0]) ** 2 + (pos[1] - self.animating_pv[3][1])
                if d_sq > 2 * self.stone_size ** 2:  # move too far from where it was activated
                    self.set_animating_pv(None, None)  # any click kills PV from label/move
            self.last_mouse_pos = pos

    def on_touch_up(self, touch):
        if ("button" in touch.profile and touch.button != "left") or not self.gridpos_x:
            return
        katrain = self.katrain
        if self.selecting_region_of_interest:
            if len(self.region_of_interest) == 4:
                self.katrain.game.set_region_of_interest(self.region_of_interest)
                self.region_of_interest = []
                self.selecting_region_of_interest = False

        elif self.ghost_stone and ("button" not in touch.profile or touch.button == "left"):
            game = self.katrain and self.katrain.game
            current_node = game and self.katrain.game.current_node
            if (
                current_node
                and not current_node.children
                and not self.katrain.next_player_info.ai
                and not self.katrain.controls.timer.paused
                and self.katrain.play_analyze_mode == MODE_PLAY
                and self.katrain.config("timer/main_time", 0) * 60 - game.main_time_used <= 0
                and current_node.time_used < self.katrain.config("timer/minimal_use", 0)
            ):
                self.katrain.controls.set_status(
                    i18n._("move too fast").format(num=self.katrain.config("timer/minimal_use", 0)), STATUS_TEACHING
                )
            else:
                katrain("play", self.ghost_stone)
                self.play_stone_sound()
        elif not self.ghost_stone:
            xd, xp = self._find_closest(touch.x, self.gridpos_x)
            yd, yp = self._find_closest(touch.y, self.gridpos_y)

            nodes_here = [
                node for node in katrain.game.current_node.nodes_from_root if node.move and node.move.coords == (xp, yp)
            ]
            if nodes_here and max(yd, xd) < self.grid_size / 2:  # load old comment
                if touch.is_double_tap:  # navigate to move
                    katrain.game.set_current_node(nodes_here[-1].parent)
                    katrain.update_state()
                else:  # load comments & pv
                    katrain.log(
                        f"\nAnalysis:\n{json_truncate_arrays(nodes_here[-1].analysis,lim=5)}", OUTPUT_EXTRA_DEBUG
                    )
                    katrain.log(
                        f"\nParent Analysis:\n{json_truncate_arrays(nodes_here[-1].parent.analysis,lim=5)}",
                        OUTPUT_EXTRA_DEBUG,
                    )
                    katrain.log(
                        f"\nRoot Stats:\n{json_truncate_arrays(nodes_here[-1].analysis['root'],lim=5)}", OUTPUT_DEBUG
                    )
                    katrain.controls.info.text = nodes_here[-1].comment(sgf=True)
                    katrain.controls.active_comment_node = nodes_here[-1]
                    if nodes_here[-1].parent.analysis_exists:
                        self.set_animating_pv(nodes_here[-1].parent.candidate_moves[0]["pv"], nodes_here[-1].parent)

        self.ghost_stone = None
        self.redraw_hover_contents_trigger()  # remove ghost

    # drawing functions
    def redraw(self, *_args):
        self.draw_board()
        self.draw_board_contents()

    def draw_stone(self, x, y, player, alpha=1, innercol=None, evalcol=None, evalscale=1.0, scale=1.0):
        stone_size = self.stone_size * scale
        Color(1, 1, 1, alpha)
        Rectangle(
            pos=(self.gridpos_x[x] - stone_size, self.gridpos_y[y] - stone_size),
            size=(2 * stone_size, 2 * stone_size),
            texture=cached_texture(Theme.STONE_TEXTURE[player]),
        )
        if evalcol:
            eval_radius = math.sqrt(evalscale)  # scale area by evalscale
            evalsize = self.stone_size * (
                Theme.EVAL_DOT_MIN_SIZE + eval_radius * (Theme.EVAL_DOT_MAX_SIZE - Theme.EVAL_DOT_MIN_SIZE)
            )
            Color(*evalcol)
            Rectangle(
                pos=(self.gridpos_x[x] - evalsize, self.gridpos_y[y] - evalsize),
                size=(2 * evalsize, 2 * evalsize),
                texture=cached_texture(Theme.EVAL_DOT_TEXTURE),
            )
        if innercol:
            Color(*innercol)
            inner_size = stone_size * 0.8
            Rectangle(
                pos=(self.gridpos_x[x] - inner_size, self.gridpos_y[y] - inner_size),
                size=(2 * inner_size, 2 * inner_size),
                texture=cached_texture(Theme.LAST_MOVE_TEXTURE),
            )

    def eval_color(self, points_lost, show_dots_for_class: List[bool] = None) -> Optional[List[float]]:
        i = evaluation_class(points_lost, self.trainer_config["eval_thresholds"])
        colors = Theme.EVAL_COLORS[self.trainer_config["theme"]]
        if show_dots_for_class is None or show_dots_for_class[i]:
            return colors[i]

    def draw_board(self, *_args):
        if not (self.katrain and self.katrain.game):
            return
        katrain = self.katrain
        board_size_x, board_size_y = katrain.game.board_size

        with self.canvas.before:
            self.canvas.before.clear()
            # set up margins and grid lines
            if self.draw_coords_enabled:
                grid_spaces_margin_x = [1.5, 0.75]  # left, right
                grid_spaces_margin_y = [1.5, 0.75]  # bottom, top
            else:  # no coordinates means remove the offset
                grid_spaces_margin_x = [0.75, 0.75]  # left, right
                grid_spaces_margin_y = [0.75, 0.75]  # bottom, top
            x_grid_spaces = board_size_x - 1 + sum(grid_spaces_margin_x)
            y_grid_spaces = board_size_y - 1 + sum(grid_spaces_margin_y)
            self.grid_size = min(self.width / x_grid_spaces, self.height / y_grid_spaces)
            board_width_with_margins = x_grid_spaces * self.grid_size
            board_height_with_margins = y_grid_spaces * self.grid_size
            extra_px_margin_x = (self.width - board_width_with_margins) / 2
            extra_px_margin_y = (self.height - board_height_with_margins) / 2
            self.stone_size = self.grid_size * Theme.STONE_SIZE

            self.gridpos_x = [
                self.pos[0] + extra_px_margin_x + math.floor((grid_spaces_margin_x[0] + i) * self.grid_size + 0.5)
                for i in range(board_size_x)
            ]
            self.gridpos_y = [
                self.pos[1] + extra_px_margin_y + math.floor((grid_spaces_margin_y[0] + i) * self.grid_size + 0.5)
                for i in range(board_size_y)
            ]

            if katrain.game.insert_mode:
                Color(*Theme.INSERT_BOARD_COLOR_TINT)  # dreamy
            else:
                Color(*Theme.BOARD_COLOR_TINT)  # image is a bit too light
            Rectangle(
                pos=(
                    self.gridpos_x[0] - self.grid_size * grid_spaces_margin_x[0],
                    self.gridpos_y[0] - self.grid_size * grid_spaces_margin_y[0],
                ),
                size=(self.grid_size * x_grid_spaces, self.grid_size * y_grid_spaces),
                texture=cached_texture(Theme.BOARD_TEXTURE),
            )

            Color(*Theme.LINE_COLOR)
            for i in range(board_size_x):
                Line(points=[(self.gridpos_x[i], self.gridpos_y[0]), (self.gridpos_x[i], self.gridpos_y[-1])])
            for i in range(board_size_y):
                Line(points=[(self.gridpos_x[0], self.gridpos_y[i]), (self.gridpos_x[-1], self.gridpos_y[i])])

            # star points
            def star_point_coords(size):
                star_point_pos = 3 if size <= 11 else 4
                if size < 7:
                    return []
                return [star_point_pos - 1, size - star_point_pos] + (
                    [int(size / 2)] if size % 2 == 1 and size > 7 else []
                )

            starpt_size = self.grid_size * Theme.STARPOINT_SIZE
            for x in star_point_coords(board_size_x):
                for y in star_point_coords(board_size_y):
                    draw_circle((self.gridpos_x[x], self.gridpos_y[y]), starpt_size, Theme.LINE_COLOR)

            # coordinates
            if self.draw_coords_enabled:
                Color(0.25, 0.25, 0.25)
                coord_offset = self.grid_size * 1.5 / 2
                for i in range(board_size_x):
                    draw_text(
                        pos=(self.gridpos_x[i], self.gridpos_y[0] - coord_offset),
                        text=Move.GTP_COORD[i],
                        font_size=self.grid_size / 1.5,
                        font_name="Roboto",
                    )
                for i in range(board_size_y):
                    draw_text(
                        pos=(self.gridpos_x[0] - coord_offset, self.gridpos_y[i]),
                        text=str(i + 1),
                        font_size=self.grid_size / 1.5,
                        font_name="Roboto",
                    )

    def draw_board_contents(self, *_args):
        if not (self.katrain and self.katrain.game):
            return
        katrain = self.katrain
        board_size_x, board_size_y = katrain.game.board_size
        if len(self.gridpos_x) < board_size_x or len(self.gridpos_y) < board_size_y:
            return  # race condition
        show_n_eval = self.trainer_config["eval_off_show_last"]

        with self.canvas:
            self.canvas.clear()
            # stones
            current_node = katrain.game.current_node
            game_ended = katrain.game.end_result
            full_eval_on = katrain.analysis_controls.eval.active
            all_dots_off = katrain.analysis_controls.eval.checkbox.slashed
            has_stone = {}
            drawn_stone = {}
            for m in katrain.game.stones:
                has_stone[m.coords] = m.player

            show_dots_for = {
                p: self.trainer_config["eval_show_ai"] or katrain.players_info[p].human for p in Move.PLAYERS
            }
            show_dots_for_class = self.trainer_config["show_dots"]
            nodes = katrain.game.current_node.nodes_from_root
            realized_points_lost = None

            for i, node in enumerate(nodes[::-1]):  # reverse order!
                points_lost = node.points_lost
                evalscale = 1
                if points_lost and realized_points_lost:
                    if points_lost <= 0.5 and realized_points_lost <= 1.5:
                        evalscale = 0
                    else:
                        evalscale = min(1, max(0, realized_points_lost / points_lost))
                placements = node.placements
                for m in node.moves + placements:
                    if has_stone.get(m.coords) and not drawn_stone.get(m.coords):  # skip captures, last only for
                        move_eval_on = (
                            not all_dots_off and show_dots_for.get(m.player) and (i < show_n_eval or full_eval_on)
                        )
                        if move_eval_on and points_lost is not None:
                            evalcol = self.eval_color(points_lost, show_dots_for_class)
                        else:
                            evalcol = None
                        inner = Theme.STONE_COLORS[m.opponent] if i == 0 and m not in placements else None
                        drawn_stone[m.coords] = m.player
                        self.draw_stone(
                            x=m.coords[0],
                            y=m.coords[1],
                            player=m.player,
                            innercol=inner,
                            evalcol=evalcol,
                            evalscale=evalscale,
                        )
                realized_points_lost = node.parent_realized_points_lost

            if katrain.game.current_node.is_root and katrain.debug_level >= 3:  # secret ;)
                for y in range(0, board_size_y):
                    evalcol = self.eval_color(16 * y / board_size_y)
                    self.draw_stone(0, y, "B", evalcol=evalcol, evalscale=y / (board_size_y - 1))
                    self.draw_stone(1, y, "B", innercol=Theme.STONE_COLORS["W"], evalcol=evalcol)
                    self.draw_stone(2, y, "W", evalcol=evalcol, evalscale=y / (board_size_y - 1))
                    self.draw_stone(3, y, "W", innercol=Theme.STONE_COLORS["B"], evalcol=evalcol)

            # ownership - allow one move out of date for smooth animation
            ownership = current_node.ownership or (current_node.parent and current_node.parent.ownership)
            if katrain.analysis_controls.ownership.active and ownership:
                rsz = self.grid_size * 0.2
                if (
                    current_node.children
                    and katrain.controls.status_state[1] == STATUS_TEACHING
                    and current_node.children[-1].auto_undo
                    and current_node.children[-1].ownership
                ):  # loss
                    loss_grid = var_to_grid(
                        [a - b for a, b in zip(current_node.children[-1].ownership, ownership)],
                        (board_size_x, board_size_y),
                    )

                    for y in range(board_size_y - 1, -1, -1):
                        for x in range(board_size_x):
                            loss = max(0, (-1 if current_node.children[-1].move.player == "B" else 1) * loss_grid[y][x])
                            if loss > 0:
                                Color(*Theme.EVAL_COLORS[self.trainer_config["theme"]][1][:3], loss)
                                Rectangle(
                                    pos=(self.gridpos_x[x] - rsz / 2, self.gridpos_y[y] - rsz / 2), size=(rsz, rsz)
                                )
                else:
                    ownership_grid = var_to_grid(ownership, (board_size_x, board_size_y))
                    for y in range(board_size_y - 1, -1, -1):
                        for x in range(board_size_x):
                            ix_owner = "B" if ownership_grid[y][x] > 0 else "W"
                            if ix_owner != (has_stone.get((x, y), -1)):
                                Color(*Theme.STONE_COLORS[ix_owner][:3], abs(ownership_grid[y][x]))
                                Rectangle(
                                    pos=(self.gridpos_x[x] - rsz / 2, self.gridpos_y[y] - rsz / 2), size=(rsz, rsz)
                                )

            policy = current_node.policy
            if (
                not policy
                and current_node.parent
                and current_node.parent.policy
                and katrain.last_player_info.ai
                and katrain.next_player_info.ai
            ):
                policy = (
                    current_node.parent.policy
                )  # in the case of AI self-play we allow the policy to be one step out of date

            pass_btn = katrain.board_controls.pass_btn
            pass_btn.canvas.after.clear()
            if katrain.analysis_controls.policy.active and policy:
                policy_grid = var_to_grid(policy, (board_size_x, board_size_y))
                best_move_policy = max(*policy)
                colors = Theme.EVAL_COLORS[self.trainer_config["theme"]]
                text_lb = 0.01 * 0.01
                for y in range(board_size_y - 1, -1, -1):
                    for x in range(board_size_x):
                        move_policy = policy_grid[y][x]
                        if move_policy < 0:
                            continue
                        pol_order = max(0, 5 + int(math.log10(max(1e-9, move_policy - 1e-9))))
                        if move_policy > text_lb:
                            draw_circle(
                                (self.gridpos_x[x], self.gridpos_y[y]),
                                self.stone_size * Theme.HINT_SCALE * 0.98,
                                Theme.APPROX_BOARD_COLOR,
                            )
                            scale = 0.95
                        else:
                            scale = 0.5
                        draw_circle(
                            (self.gridpos_x[x], self.gridpos_y[y]),
                            Theme.HINT_SCALE * self.stone_size * scale,
                            (*colors[pol_order][:3], Theme.POLICY_ALPHA),
                        )
                        if move_policy > text_lb:
                            Color(*Theme.HINT_TEXT_COLOR)
                            draw_text(
                                pos=(self.gridpos_x[x], self.gridpos_y[y]),
                                text=f"{100 * move_policy :.2f}"[:4] + "%",
                                font_name="Roboto",
                                font_size=self.grid_size / 4,
                                halign="center",
                            )
                        if move_policy == best_move_policy:
                            Color(*Theme.TOP_MOVE_BORDER_COLOR[:3], Theme.POLICY_ALPHA)
                            Line(circle=(self.gridpos_x[x], self.gridpos_y[y], self.stone_size - dp(1.2)), width=dp(2))

                with pass_btn.canvas.after:
                    move_policy = policy[-1]
                    pol_order = 5 - int(-math.log10(max(1e-9, move_policy - 1e-9)))
                    if pol_order >= 0:
                        draw_circle(
                            (pass_btn.pos[0] + pass_btn.width / 2, pass_btn.pos[1] + pass_btn.height / 2),
                            pass_btn.height / 2,
                            (*colors[pol_order][:3], Theme.GHOST_ALPHA),
                        )

            # pass circle
            passed = len(nodes) > 1 and current_node.is_pass
            if passed or game_ended:
                if game_ended:
                    text = game_ended
                    katrain.controls.timer.paused = True
                else:
                    text = i18n._("board-pass")
                Color(*Theme.PASS_CIRCLE_COLOR)
                center = (self.gridpos_x[int(board_size_x / 2)], self.gridpos_y[int(board_size_y / 2)])
                size = min(self.width, self.height) * 0.227
                Ellipse(pos=(center[0] - size / 2, center[1] - size / 2), size=(size, size))
                Color(*Theme.PASS_CIRCLE_TEXT_COLOR)
                draw_text(pos=center, text=text, font_size=size * 0.25, halign="center")

        self.redraw_hover_contents_trigger()

    def draw_roi_box(self, region_of_interest, width=2):
        xmin, xmax, ymin, ymax = region_of_interest
        Color(*Theme.REGION_BORDER_COLOR)
        Line(
            rectangle=(
                self.gridpos_x[xmin] - self.grid_size / 3,
                self.gridpos_y[ymin] - self.grid_size / 3,
                (xmax - xmin + 2 / 3) * self.grid_size,
                (ymax - ymin + 2 / 3) * self.grid_size,
            ),
            width=width,
        )

    def draw_hover_contents(self, *_args):
        ghost_alpha = Theme.GHOST_ALPHA
        katrain = self.katrain
        game_ended = katrain.game.end_result
        current_node = katrain.game.current_node
        next_player = current_node.next_player

        board_size_x, board_size_y = katrain.game.board_size
        if len(self.gridpos_x) < board_size_x or len(self.gridpos_y) < board_size_y:
            return  # race condition

        with self.canvas.after:
            self.canvas.after.clear()

            self.active_pv_moves = []
            # hints or PV
            hint_moves = []
            if (
                katrain.analysis_controls.hints.active
                and not katrain.analysis_controls.policy.active
                and not game_ended
            ):
                hint_moves = current_node.candidate_moves
            elif katrain.controls.status_state[1] == STATUS_TEACHING:  # show score hint for teaching  undo
                hint_moves = [
                    m
                    for m in current_node.candidate_moves
                    for c in current_node.children
                    if c.move and c.auto_undo and c.move.gtp() == m["move"]
                ]

            top_move_coords = None
            child_moves = {c.move.gtp() for c in current_node.children if c.move}
            if hint_moves:
                low_visits_threshold = katrain.config("trainer/low_visits", 25)
                top_moves_show = [
                    opt
                    for opt in [
                        katrain.config("trainer/top_moves_show"),
                        katrain.config("trainer/top_moves_show_secondary"),
                    ]
                    if opt in TOP_MOVE_OPTIONS and opt != TOP_MOVE_NOTHING
                ]
                for move_dict in hint_moves:
                    move = Move.from_gtp(move_dict["move"])
                    if move.coords is not None:
                        engine_best_move = move_dict.get("order", 99) == 0
                        scale = Theme.HINT_SCALE
                        text_on = True
                        alpha = Theme.HINTS_ALPHA
                        if (
                            move_dict["visits"] < low_visits_threshold
                            and not engine_best_move
                            and not move_dict["move"] in child_moves
                        ):
                            scale = Theme.UNCERTAIN_HINT_SCALE
                            text_on = False
                            alpha = Theme.HINTS_LO_ALPHA

                        if "pv" in move_dict:
                            self.active_pv_moves.append((move.coords, move_dict["pv"], current_node))
                        else:
                            katrain.log(f"PV missing for move_dict {move_dict}", OUTPUT_DEBUG)
                        evalsize = self.stone_size * scale
                        evalcol = self.eval_color(move_dict["pointsLost"])
                        if text_on and top_moves_show:  # remove grid lines using a board colored circle
                            draw_circle(
                                (self.gridpos_x[move.coords[0]], self.gridpos_y[move.coords[1]]),
                                self.stone_size * scale * 0.98,
                                Theme.APPROX_BOARD_COLOR,
                            )

                        Color(*evalcol[:3], alpha)
                        Rectangle(
                            pos=(self.gridpos_x[move.coords[0]] - evalsize, self.gridpos_y[move.coords[1]] - evalsize),
                            size=(2 * evalsize, 2 * evalsize),
                            texture=cached_texture(Theme.TOP_MOVE_TEXTURE),
                        )
                        if text_on and top_moves_show:  # TODO: faster if not sized?
                            keys = {"size": self.grid_size / 3, "smallsize": self.grid_size / 3.33}
                            player_sign = current_node.player_sign(next_player)
                            if len(top_moves_show) == 1:
                                fmt = "[size={size:.0f}]{" + top_moves_show[0] + "}[/size]"
                            else:
                                fmt = (
                                    "[size={size:.0f}]{"
                                    + top_moves_show[0]
                                    + "}[/size]\n[size={smallsize:.0f}]{"
                                    + top_moves_show[1]
                                    + "}[/size]"
                                )

                            keys[TOP_MOVE_DELTA_SCORE] = (
                                "0.0" if -0.05 < move_dict["pointsLost"] < 0.05 else f"{-move_dict['pointsLost']:+.1f}"
                            )
                            keys[TOP_MOVE_SCORE] = f"{player_sign * move_dict['scoreLead']:.1f}"
                            winrate = move_dict["winrate"] if player_sign == 1 else 1 - move_dict["winrate"]
                            keys[TOP_MOVE_WINRATE] = f"{winrate*100:.1f}"
                            keys[TOP_MOVE_DELTA_WINRATE] = f"{-move_dict['winrateLost']:+.1%}"
                            keys[TOP_MOVE_VISITS] = format_visits(move_dict["visits"])
                            Color(*Theme.HINT_TEXT_COLOR)
                            draw_text(
                                pos=(self.gridpos_x[move.coords[0]], self.gridpos_y[move.coords[1]]),
                                text=fmt.format(**keys),
                                font_name="Roboto",
                                markup=True,
                                line_height=0.85,
                                halign="center",
                            )

                        if engine_best_move:
                            top_move_coords = move.coords
                            Color(*Theme.TOP_MOVE_BORDER_COLOR)
                            Line(
                                circle=(
                                    self.gridpos_x[move.coords[0]],
                                    self.gridpos_y[move.coords[1]],
                                    self.stone_size - dp(1.2),
                                ),
                                width=dp(1.2),
                            )

            # children of current moves in undo / review
            if katrain.analysis_controls.show_children.active:
                for child_node in current_node.children:
                    move = child_node.move
                    if move and move.coords is not None:
                        if child_node.analysis_exists:
                            self.active_pv_moves.append(
                                (move.coords, [move.gtp()] + child_node.candidate_moves[0]["pv"], current_node)
                            )

                        if move.coords != top_move_coords:  # for contrast
                            dashed_width = 18
                            Color(*Theme.NEXT_MOVE_DASH_CONTRAST_COLORS[child_node.player])
                            Line(
                                circle=(
                                    self.gridpos_x[move.coords[0]],
                                    self.gridpos_y[move.coords[1]],
                                    self.stone_size - dp(1.2),
                                ),
                                width=dp(1.2),
                            )
                        else:
                            dashed_width = 10
                        Color(*Theme.STONE_COLORS[child_node.player])
                        for s in range(0, 360, 30):
                            Line(
                                circle=(
                                    self.gridpos_x[move.coords[0]],
                                    self.gridpos_y[move.coords[1]],
                                    self.stone_size - dp(1.2),
                                    s,
                                    s + dashed_width,
                                ),
                                width=dp(1.2),
                            )

            if self.selecting_region_of_interest and len(self.region_of_interest) == 4:
                x1, x2, y1, y2 = self.region_of_interest
                self.draw_roi_box([min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)], width=dp(2))
            else:
                # hover next move ghost stone
                if self.ghost_stone:
                    self.draw_stone(*self.ghost_stone, next_player, alpha=ghost_alpha)

                animating_pv = self.animating_pv
                if animating_pv:
                    pv, node, start_time, _ = animating_pv
                    delay = self.katrain.config("general/anim_pv_time", 0.5)
                    up_to_move = (time.time() - start_time) / delay
                    self.draw_pv(pv, node, up_to_move)

                if self.katrain.game.region_of_interest:
                    self.draw_roi_box(self.katrain.game.region_of_interest, width=dp(1.25))

    def animate_pv(self, _dt):
        if self.animating_pv:
            self.redraw_hover_contents_trigger()

    def draw_pv(self, pv, node, up_to_move):
        katrain = self.katrain
        next_last_player = [node.next_player, Move.opponent_player(node.next_player)]
        cn = katrain.game.current_node
        if node != cn and node.parent != cn:
            hide_node = cn
            while hide_node and hide_node.move and hide_node != node:
                if not hide_node.move.is_pass:
                    pos = (self.gridpos_x[hide_node.move.coords[0]], self.gridpos_y[hide_node.move.coords[1]])
                    draw_circle(pos, self.stone_size, [0.85, 0.68, 0.40, 0.8])
                hide_node = hide_node.parent
        for i, gtpmove in enumerate(pv):
            if i > up_to_move:
                return
            move_player = next_last_player[i % 2]
            coords = Move.from_gtp(gtpmove).coords
            if coords is None:  # tee-hee
                sizefac = katrain.board_controls.pass_btn.size[1] / 2 / self.stone_size
                board_coords = [
                    katrain.board_controls.pass_btn.pos[0]
                    + katrain.board_controls.pass_btn.size[0]
                    + self.stone_size * sizefac,
                    katrain.board_controls.pass_btn.pos[1] + katrain.board_controls.pass_btn.size[1] / 2,
                ]
            else:
                board_coords = (self.gridpos_x[coords[0]], self.gridpos_y[coords[1]])
                sizefac = 1

            stone_size = self.stone_size * sizefac
            Color(1, 1, 1, 1)
            Rectangle(  # not sure why the -1 here, but seems to center better
                pos=(board_coords[0] - stone_size - 1, board_coords[1] - stone_size),
                size=(2 * stone_size + 1, 2 * stone_size + 1),
                texture=cached_texture(Theme.STONE_TEXTURE[move_player]),
            )
            Color(*Theme.PV_TEXT_COLORS[move_player])
            draw_text(pos=board_coords, text=str(i + 1), font_size=self.grid_size * sizefac / 1.45, font_name="Roboto")

    def set_animating_pv(self, pv, node):
        if pv is None:
            self.animating_pv = None
        elif node is not None and (
            not self.animating_pv or not (self.animating_pv[0] == pv and self.animating_pv[1] == node)
        ):
            self.animating_pv = (pv, node, time.time(), self.last_mouse_pos)
        self.redraw_hover_contents_trigger()

    def show_pv_from_comments(self, pv_str):
        self.set_animating_pv(pv_str[1:].split(" "), self.katrain.controls.active_comment_node.parent)


class AnalysisDropDown(DropDown):
    def open_game_analysis_popup(self, *_args):
        analysis_popup = I18NPopup(title_key="analysis:game", size=[dp(500), dp(300)], content=ReAnalyzeGamePopup())
        analysis_popup.content.popup = analysis_popup
        analysis_popup.content.katrain = MDApp.get_running_app().gui
        analysis_popup.open()


class AnalysisControls(MDBoxLayout):
    dropdown = ObjectProperty(None)
    is_open = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.build_dropdown()

    def on_is_open(self, instance, value):
        if value:
            max_content_width = max(option.content_width for option in self.dropdown.container.children)
            self.dropdown.width = max_content_width
            self.dropdown.open(self.analysis_button)
        elif self.dropdown.attach_to:
            self.dropdown.dismiss()

    def close_dropdown(self, *largs):
        self.is_open = False

    def toggle_dropdown(self, *largs):
        self.is_open = not self.is_open

    def build_dropdown(self):
        self.dropdown = AnalysisDropDown(auto_width=False)
        self.dropdown.bind(on_dismiss=self.close_dropdown)


class BadukPanControls(MDFloatLayout):
    engine_status_col = ListProperty(Theme.ENGINE_DOWN_COLOR)
    engine_status_pondering = NumericProperty(-1)
    queries_remaining = NumericProperty(0)
