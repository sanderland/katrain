from collections import defaultdict

from kivy.graphics.context_instructions import Color
from kivy.graphics.vertex_instructions import Line, Rectangle
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, Clock, NumericProperty, ObjectProperty
from kivy.uix.dropdown import DropDown
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.app import MDApp

from katrain.gui.kivyutils import BackgroundMixin, draw_circle, draw_text
from katrain.gui.theme import Theme


class MoveTreeDropdown(DropDown):
    pass


class MoveTreeCanvas(Widget):
    scroll_view_widget = ObjectProperty(None)
    move_size = NumericProperty(5)
    dropdown = ObjectProperty(None)
    is_open = BooleanProperty(False)
    menu_selected_node = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.move_pos = {}
        self.move_xy_pos = {}
        self.bind(menu_selected_node=lambda *_args: self.scroll_view_widget.redraw_tree_trigger())
        self.build_dropdown()

    def on_is_open(self, instance, value):
        if value:
            max_content_width = max(option.content_width for option in self.dropdown.container.children)
            self.dropdown.width = max_content_width
            self.dropdown.open(self.scroll_view_widget)
        else:
            self.menu_selected_node = None
            if self.dropdown.attach_to:
                self.dropdown.dismiss()

    def close_dropdown(self, *largs):
        self.is_open = False

    def build_dropdown(self):
        self.dropdown = MoveTreeDropdown(auto_width=False)
        self.dropdown.bind(on_dismiss=self.close_dropdown)

    def set_game_node(self, node):
        katrain = MDApp.get_running_app().gui
        katrain.game.set_current_node(node)
        katrain.update_state()

    def on_touch_up(self, touch):
        selected_node = None
        is_open = False
        node, (x, y) = min(
            self.move_xy_pos.items(), key=lambda n_xy: abs(n_xy[1][0] - touch.x) + abs(n_xy[1][1] - touch.y)
        )
        if max(abs(x - touch.x), abs(y - touch.y)) <= (self.move_size / 2):
            if "button" not in touch.profile or touch.button == "left":
                self.set_game_node(node)
            elif touch.button == "right" and not node.is_root:
                is_open = True
                selected_node = node
        self.is_open = is_open
        self.menu_selected_node = selected_node

    def delete_selected_node(self):
        selected_node = self.menu_selected_node or self.scroll_view_widget.current_node
        if selected_node and selected_node.parent:
            if selected_node.shortcut_from:
                parent = selected_node.shortcut_from
                via = [v for m, v in parent.shortcuts_to if m == selected_node]
                selected_node.remove_shortcut()
                if via:  # should always be
                    parent.children.remove(via[0])
            else:
                parent = selected_node.parent
                parent.children.remove(selected_node)
            self.set_game_node(parent)
        self.is_open = False

    def make_selected_node_main_branch(self):
        selected_node = self.menu_selected_node or self.scroll_view_widget.current_node
        if selected_node and selected_node.parent:
            node = selected_node
            while node.parent is not None:
                node.parent.children.remove(node)
                node.parent.children.insert(0, node)
                node = node.parent
            self.set_game_node(selected_node)
        self.is_open = False

    def toggle_selected_node_collapse(self):
        selected_node = self.menu_selected_node or self.scroll_view_widget.current_node
        if selected_node and selected_node.parent:
            if selected_node.shortcut_from:
                selected_node.remove_shortcut()
            else:  # find branching point
                node = selected_node.parent
                while len(node.children) == 1 and not node.is_root and not node.shortcut_from:
                    node = node.parent
                node.add_shortcut(selected_node)
            self.scroll_view_widget.redraw_tree_trigger()

    def switch_branch(self, direction=1):
        pos = self.move_pos.get(self.scroll_view_widget.current_node)
        if not self.scroll_view_widget or not pos:
            return
        same_x_moves = sorted([(y, n) for n, (x, y) in self.move_pos.items() if x == pos[0]])
        new_index = next((i for i, (y, n) in enumerate(same_x_moves) if y == pos[1]), 0) + direction
        if new_index < 0 or new_index >= len(same_x_moves):
            return
        self.set_game_node(same_x_moves[new_index][1])

    def draw_move_tree(self, current_node, insert_node):
        if not self.scroll_view_widget or not current_node:
            return
        spacing = 5
        moves_vert = 3
        self.move_size = (self.scroll_view_widget.min_height - (moves_vert + 1) * spacing) / moves_vert

        root = current_node.root

        def children_with_shortcuts(move):
            shortcuts = move.shortcuts_to
            via = {v: m for m, v in shortcuts}  # children that are shortcut
            return [m if m not in via else via[m] for m in move.ordered_children]

        self.move_pos = {root: (0, 0)}
        stack = children_with_shortcuts(root)[::-1]
        next_y_pos = defaultdict(int)  # x pos -> max y pos
        children = defaultdict(list)  # since AI self-play etc may modify the tree between layout and draw!
        children[root] = [*stack]
        while stack:
            move = stack.pop()
            if move.shortcut_from:
                parent = move.shortcut_from
            else:
                parent = move.parent

            if parent:
                x = self.move_pos[parent][0] + 1
            else:
                x = 0
            y = max(next_y_pos[x], self.move_pos[parent][1])
            next_y_pos[x] = y + 1
            next_y_pos[x - 1] = max(next_y_pos[x], next_y_pos[x - 1])
            self.move_pos[move] = (x, y)
            children[move] = children_with_shortcuts(move)
            stack += children[move][::-1]  # stack, so push top child last to process first

        def draw_stone(pos, player, special_color=None):
            draw_circle(pos, self.move_size / 2 - 0.5, (special_color or Theme.STONE_COLORS[player]))
            Color(*Theme.MOVE_TREE_STONE_OUTLINE_COLORS[player])
            Line(circle=(*pos, self.move_size / 2), width=1)

        def coord_pos(coord):
            return (coord + 0.5) * (spacing + self.move_size) + spacing / 2

        self.width = coord_pos(max(x + 0.5 for x, y in self.move_pos.values()))
        self.height = coord_pos(max(y + 0.5 for x, y in self.move_pos.values()))

        def xy_pos(x, y):
            return coord_pos(x), self.height - coord_pos(y)

        self.move_xy_pos = {n: xy_pos(x, y) for n, (x, y) in self.move_pos.items()}

        special_nodes = {current_node: Theme.MOVE_TREE_CURRENT, self.menu_selected_node: Theme.MOVE_TREE_SELECTED}

        if insert_node:
            special_nodes[insert_node.parent] = Theme.MOVE_TREE_INSERT_NODE_PARENT
            insert_path = current_node
            while insert_path != insert_node.parent and insert_path.parent:
                special_nodes[insert_path] = (
                    Theme.MOVE_TREE_INSERT_CURRENT if insert_path == current_node else Theme.MOVE_TREE_INSERT_OTHER
                )
                insert_path = insert_path.parent

        with self.canvas:
            self.canvas.clear()
            Color(*Theme.MOVE_TREE_LINE)
            for node, (x, y) in self.move_xy_pos.items():
                for ci, c in enumerate(children[node]):
                    cx, cy = self.move_xy_pos[c]
                    Line(points=[x, y, x, cy, cx, cy], width=1)

            for node, pos in self.move_xy_pos.items():
                if node in special_nodes:
                    Color(*special_nodes[node])
                    Rectangle(
                        pos=[c - self.move_size / 2 - spacing / 2 for c in self.move_xy_pos[node]],
                        size=(self.move_size + spacing, self.move_size + spacing),
                    )
                collapsed_color = Theme.MOVE_TREE_COLLAPSED if node.shortcut_from else None
                draw_stone(pos, node.player, collapsed_color)
                text = str(node.depth)
                Color(*Theme.STONE_COLORS["W" if node.player == "B" and not node.shortcut_from else "B"])
                draw_text(pos=pos, text=text, font_size=self.move_size * 1.75 / (1 + 1 * len(text)), font_name="Roboto")

            if current_node in self.move_xy_pos:
                self.scroll_view_widget.scroll_to_pixel(*self.move_xy_pos[current_node])


class MoveTree(ScrollView, BackgroundMixin):
    current_node = ObjectProperty(None)
    min_height = NumericProperty(dp(50))  # non-expanded height, to determine the node size

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.insert_node = None
        self.redraw_tree_trigger = Clock.create_trigger(
            lambda _dt: self.move_tree_canvas.draw_move_tree(self.current_node, self.insert_node), 0.1
        )
        self.bind(current_node=self.redraw_tree_trigger, size=self.redraw_tree_trigger)

    def redraw(self):
        self.redraw_tree_trigger()

    def switch_branch(self, direction):
        self.move_tree_canvas.switch_branch(direction)

    def delete_selected_node(self):
        self.move_tree_canvas.delete_selected_node()
        self.redraw_tree_trigger()

    def make_selected_node_main_branch(self):
        self.move_tree_canvas.make_selected_node_main_branch()
        self.redraw_tree_trigger()

    def toggle_selected_node_collapse(self):
        self.move_tree_canvas.toggle_selected_node_collapse()
        self.redraw_tree_trigger()

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

    # disable mousewheel
    def on_scroll_start(self, touch, check_children=True):
        if "button" in touch.profile and touch.button.startswith("scroll"):
            return False
        return super().on_scroll_start(touch, check_children)


Builder.load_string(
    """
#:import Theme katrain.gui.theme.Theme
#:import WHITE katrain.gui.theme.WHITE
#:import LIGHT_GREY katrain.gui.theme.LIGHT_GREY
<MoveTree>:
    background_color: Theme.BOX_BACKGROUND_COLOR
    move_tree_canvas: move_tree_canvas
    MoveTreeCanvas:
        scroll_view_widget: root
        id: move_tree_canvas
        size_hint: None, None

<MoveTreeDropdownItem@MenuItem>:
    canvas.before:
        Color:
            rgba: WHITE
        Line:
            points: self.x, self.y, self.x, self.y+self.height
        Color:
            rgba: LIGHT_GREY
        Line
            points: self.x,self.y,self.x+self.width,self.y
            width: 1

<MoveTreeDropdown>:
    katrain: app.gui
    MoveTreeDropdownItem:
        text: i18n._("Delete Node")
        icon: 'delete.png'
        shortcut: 'Ctr+Del'
        on_action: root.katrain.controls.move_tree.delete_selected_node()
        -background_color: Theme.LIGHTER_BACKGROUND_COLOR
        -height: dp(45)
        -width_margin: 1.6
    MoveTreeDropdownItem:
        text: i18n._("Make Main Branch")
        icon: 'Branch.png'
        shortcut: 'PgUp'
        on_action: root.katrain.controls.move_tree.make_selected_node_main_branch()
        -background_color: Theme.LIGHTER_BACKGROUND_COLOR
        -height: dp(45)
        -width_margin: 1.6
    MoveTreeDropdownItem:
        text: i18n._("Toggle Collapse Branch")
        icon: 'Collapse.png'
        shortcut: 'c'
        on_action: root.katrain.controls.move_tree.toggle_selected_node_collapse()
        -background_color: Theme.LIGHTER_BACKGROUND_COLOR
        -height: dp(45)
        -width_margin: 1.6
"""
)
