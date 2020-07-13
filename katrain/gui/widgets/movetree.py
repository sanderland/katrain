from collections import defaultdict

from kivy.graphics.context_instructions import Color
from kivy.graphics.vertex_instructions import Line, Rectangle
from kivy.lang import Builder
from kivy.properties import ObjectProperty, Clock, DictProperty, NumericProperty, BooleanProperty
from kivy.uix.dropdown import DropDown
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.app import MDApp

from katrain.core.game_node import GameNode
from katrain.gui.kivyutils import BackgroundMixin, draw_circle, draw_text
from katrain.gui.style import (
    WHITE,
    STONE_COLORS,
    LIGHTGREY,
    BACKGROUND_COLOR,
    OUTLINE_COLORS,
    LIGHTER_BACKGROUND_COLOR,
    YELLOW,
    STONE_TEXT_COLORS,
)


class MoveTreeDropdown(DropDown):
    def open(self, widget, delta_pos):
        if self.attach_to is not None:
            self.attach_to.unbind(pos=self._reposition, size=self._reposition)
            self.parent.remove_widget(self)
        self._win = widget.get_parent_window()
        self.attach_to = widget
        self.delta_pos = delta_pos
        widget.bind(pos=self._reposition, size=self._reposition)
        self._reposition()
        self._win.add_widget(self)

    def _reposition(self, *largs):
        # calculate the coordinate of the attached widget in the window
        # coordinate system
        win = self._win
        if not win or not self.attach_to or not self.delta_pos:
            return
        widget = self.attach_to
        wx, wy = widget.to_window(*widget.pos)
        x, y = wx + self.delta_pos[0], wy + self.delta_pos[1]
        if x + self.width > win.width:
            x = win.width - self.width
        self.x = x
        self.y = y

class MoveTreeCanvas(Widget):
    scroll_view_widget = ObjectProperty(None)
    move_size = NumericProperty(5)
    dropdown = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.move_pos = {}
        self.move_xy_pos = {}
        self.menu_selected_node = None
        self.build_dropdown()

    def build_dropdown(self):
        self.dropdown = MoveTreeDropdown(auto_width=False)

    def set_game_node(self, node):
        katrain = MDApp.get_running_app().gui
        katrain.game.set_current_node(node)
        katrain.update_state()

    def on_touch_up(self, touch):
        self.menu_selected_node = None
        node, (x, y) = min(
            self.move_xy_pos.items(), key=lambda n_xy: abs(n_xy[1][0] - touch.x) + abs(n_xy[1][1] - touch.y)
        )
        if max(abs(x - touch.x), abs(y - touch.y)) <= (self.move_size / 2):
            if "button" not in touch.profile or touch.button == "left":
                self.set_game_node(node)
            elif touch.button == "right":
                self.dropdown.width = max(option.content_width for option in self.dropdown.container.children)
                self.menu_selected_node = node
                dx,dy = self.move_xy_pos[node]
                self.dropdown.open(self.scroll_view_widget, [dx,dy-self.move_size] )
        else:
            self.dropdown.dismiss()

    def delete_selected_node(self):
        print(self.menu_selected_node, self.menu_selected_node.move)
        self.menu_selected_node = None

    def switch_branch(self, direction=1):
        pos = self.move_pos.get(self.scroll_view_widget.current_node)
        if not self.scroll_view_widget:
            return
        same_x_moves = sorted([(y, n) for n, (x, y) in self.move_pos.items() if x == pos[0]])
        new_index = next((i for i, (y, n) in enumerate(same_x_moves) if y == pos[1]), 0) + direction
        if new_index < 0 or new_index >= len(same_x_moves):
            return
        self.set_game_node(same_x_moves[new_index][1])

    def draw_move_tree(self, current_node):
        if not self.scroll_view_widget:
            return

        spacing = 5
        moves_vert = 3
        self.move_size = (self.scroll_view_widget.height - (moves_vert + 1) * spacing) / moves_vert

        root = current_node.root

        self.move_pos = {root: (0, 0)}
        stack = root.ordered_children[::-1]
        next_y_pos = defaultdict(int)  # x pos -> max y pos
        children = defaultdict(list)  # since AI self-play etc may modify the tree between layout and draw!
        while stack:
            move = stack.pop()
            x = move.depth
            y = max(next_y_pos[x], self.move_pos[move.parent][1])
            next_y_pos[x] = y + 1
            next_y_pos[x - 1] = max(next_y_pos[x], next_y_pos[x - 1])
            self.move_pos[move] = (x, y)
            children[move] = move.ordered_children
            for c in children[move][::-1]:  # stack, so push top child last to process first
                stack.append(c)

        def draw_stone(pos, player):
            draw_circle(pos, self.move_size / 2 - 0.5, STONE_COLORS[player])
            Color(*STONE_TEXT_COLORS[player])
            line = Line(circle=(*pos, self.move_size / 2), width=1)
            return line

        def coord_pos(coord):
            return (coord + 0.5) * (spacing + self.move_size) + spacing / 2

        self.width = coord_pos(max(x + 0.5 for x, y in self.move_pos.values()))
        self.height = coord_pos(max(y + 0.5 for x, y in self.move_pos.values()))

        def xy_pos(x, y):
            return coord_pos(x), self.height - coord_pos(y)

        self.move_xy_pos = {n: xy_pos(x, y) for n, (x, y) in self.move_pos.items()}
        circle_widgets = {}

        with self.canvas:
            self.canvas.clear()
            Color(*YELLOW)
            Rectangle(
                pos=[c - self.move_size / 2 - spacing / 2 for c in self.move_xy_pos[current_node]],
                size=(self.move_size + spacing, self.move_size + spacing),
            )
            Color(*LIGHTGREY)
            for node, (x, y) in self.move_xy_pos.items():
                for ci, c in enumerate(children[node]):
                    cx, cy = self.move_xy_pos[c]
                    Line(points=[x, y, x, cy, cx, cy], width=1)

            for node, pos in self.move_xy_pos.items():
                circle_widgets[node] = draw_stone(pos, node.player)
                text = str(node.depth)
                Color(*STONE_COLORS["W" if node.player == "B" else "B"])
                draw_text(pos=pos, text=text, font_size=self.move_size * 1.75 / (1 + 1 * len(text)), font_name="Roboto")

            self.scroll_view_widget.scroll_to_pixel(*self.move_xy_pos[current_node])
        self.circle_widgets = circle_widgets


class MoveTree(ScrollView, BackgroundMixin):
    current_node = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.redraw_tree_trigger = Clock.create_trigger(
            lambda _dt: self.move_tree_canvas.draw_move_tree(self.current_node)
        )
        self.bind(current_node=self.redraw_tree_trigger, size=self.redraw_tree_trigger)

    def switch_branch(self, direction):
        self.move_tree_canvas.switch_branch(direction)

    def delete_selected_node(self):
        self.move_tree_canvas.delete_selected_node()

    def scroll_to_pixel(self, x, y):
        if not self._viewport:
            return
        vp = self._viewport
        if vp.width > self.width:
            sx = (x - self.width / 2) / (vp.width - self.width)
            self.scroll_x = max(0, min(1, sx))
        if vp.height > self.height:
            sy = (y - self.height / 2) / (vp.height - self.height)
            self.scroll_y = max(0, min(1, sy))


Builder.load_string(
    """
<MoveTree>:
    background_color: BOX_BACKGROUND_COLOR
    move_tree_canvas: move_tree_canvas
    scroll_distance: 0 # scroll wheel is for forward/backward
    MoveTreeCanvas:
        scroll_view_widget: root
        id: move_tree_canvas
        size_hint: None, None
        
<MoveTreeDropdownItem@MenuItem>:
    background_color: LIGHTER_BACKGROUND_COLOR
    canvas.before:
        Color:
            rgba: WHITE
        Line:
            points: self.x, self.y, self.x, self.y+self.height
        Color:
            rgba: LIGHTGREY
        Line
            points: self.x,self.y,self.x+self.width,self.y
            width: 1

<MoveTreeDropdown>:
    katrain: app.gui
    MoveTreeDropdownItem:
        text: i18n._("Delete Node")
        icon: 'img/Extra.png'
        shortcut: ''
        on_action: root.katrain.controls.move_tree.delete_selected_node()
        -height: 20
    """
)
