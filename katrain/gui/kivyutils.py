from kivy.clock import Clock
from kivy.core.image import Image
from kivy.core.text import Label as CoreLabel
from kivy.core.text.markup import MarkupLabel as CoreMarkupLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Rectangle
from kivy.metrics import dp
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    ObjectProperty,
    OptionProperty,
    StringProperty,
)
from kivy.resources import resource_find
from kivy.uix.behaviors import ButtonBehavior, ToggleButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget
from kivy.animation import Animation
from kivy.app import App
from kivy.uix.checkbox import CheckBox
from kivy.uix.textinput import TextInput

from katrain.core.constants import (
    AI_STRATEGIES_RECOMMENDED_ORDER,
    GAME_TYPES,
    MODE_PLAY,
    PLAYER_AI,
    PLAYER_HUMAN,
    PLAYING_NORMAL,
    PLAYING_TEACHING,
)
from katrain.core.lang import i18n
from katrain.gui.theme import Theme


class BackgroundMixin(Widget):  # -- mixins
    background_color = ListProperty([0, 0, 0, 0])
    background_radius = NumericProperty(0)
    outline_color = ListProperty([0, 0, 0, 0])
    outline_width = NumericProperty(1)


class BackgroundLabel(BackgroundMixin, Label):
    pass


class TableCellLabel(Label):
    background_color = ListProperty([0, 0, 0, 0])
    line_width = NumericProperty(0)
    outlines = ListProperty([])
    outline_color = Theme.LINE_COLOR
    outline_width = NumericProperty(1.1)

    def __init__(self, **kwargs):
        kwargs["font_name"] = kwargs.get("font_name", i18n.font_name)
        super().__init__(**kwargs)


class TableStatLabel(TableCellLabel):
    side = StringProperty("right")
    value = NumericProperty(0)
    scale = NumericProperty(100)
    bar_color = ListProperty([0, 0, 0, 1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "outlines" not in kwargs:
            self.outlines = ["left"] if self.side == "right" else ["right"]


class TableHeaderLabel(TableCellLabel):
    outlines = ["bottom"]


class LeftButtonBehavior(ButtonBehavior):  # stops buttons etc activating on right click
    def __init__(self, **kwargs):
        self.register_event_type("on_left_release")
        self.register_event_type("on_left_press")
        super().__init__(**kwargs)

    def on_touch_down(self, touch):
        return super().on_touch_down(touch)

    def on_release(self):
        if not self.last_touch or "button" not in self.last_touch.profile or self.last_touch.button == "left":
            self.dispatch("on_left_release")
        return super().on_release()

    def on_press(self):
        if not self.last_touch or "button" not in self.last_touch.profile or self.last_touch.button == "left":
            self.dispatch("on_left_press")
        return super().on_press()

    def on_left_release(self):
        pass

    def on_left_press(self):
        pass


# -- resizeable buttons / avoid baserectangular for sizing
class SizedButton(LeftButtonBehavior, BackgroundMixin):
    text = StringProperty("")
    text_color = ListProperty(Theme.BUTTON_TEXT_COLOR)
    halign = OptionProperty("center", options=["left", "center", "right", "justify", "auto"])
    label = ObjectProperty(None)
    padding_x = NumericProperty(6)
    padding_y = NumericProperty(0)
    _font_size = NumericProperty(None)
    font_name = StringProperty(Theme.DEFAULT_FONT)

    def on_label(self, _instance, label):
        if label:
            self._setup_label(label)

    def _setup_label(self, label):
        self.bind(pos=self._sync_label, size=self._sync_label)
        self._sync_label()

    def _sync_label(self, *_args):
        lbl = self.label
        if lbl:
            lbl.pos = self.pos
            lbl.size = self.size
            lbl.text_size = self.size


class AutoSizedButton(SizedButton):
    def _setup_label(self, label):
        self.bind(pos=self._sync_label, size=self._sync_label)
        self._sync_label()

    def _sync_label(self, *_args):
        lbl = self.label
        if lbl:
            lbl.pos = self.pos
            lbl.size = self.size
            lbl.text_size = (None, self.height)


class SizedRectangleButton(SizedButton):
    pass


class AutoSizedRectangleButton(AutoSizedButton):
    pass


class ToggleButtonMixin(ToggleButtonBehavior):
    inactive_outline_color = ListProperty([0.5, 0.5, 0.5, 0])
    active_outline_color = ListProperty([1, 1, 1, 0])
    inactive_background_color = ListProperty([0.5, 0.5, 0.5, 1])
    active_background_color = ListProperty([1, 1, 1, 1])

    @property
    def active(self):
        return self.state == "down"


class SizedToggleButton(ToggleButtonMixin, SizedButton):
    pass


class SizedRectangleToggleButton(ToggleButtonMixin, SizedRectangleButton):
    pass


class AutoSizedRectangleToggleButton(ToggleButtonMixin, AutoSizedRectangleButton):
    pass


class TransparentIconButton(Button):
    color = ListProperty(Theme.TEXT_COLOR)
    icon_size = ListProperty([25, 25])
    icon = StringProperty("")
    disabled = BooleanProperty(False)


class StatsLabel(BoxLayout):
    text = StringProperty("")
    label = StringProperty("")
    color = ListProperty([1, 1, 1, 1])
    hidden = BooleanProperty(False)
    font_name = StringProperty(Theme.DEFAULT_FONT)


class MyNavigationDrawer(BoxLayout):
    state = OptionProperty("close", options=["open", "close"])
    status = StringProperty("closed")
    close_on_click = BooleanProperty(True)
    swipe_edge_width = NumericProperty(0)

    _anim = None

    def set_state(self, state="toggle", animation=True):
        if state == "toggle":
            state = "close" if self.state == "open" else "open"
        if self._anim:
            self._anim.cancel(self)
        if animation:
            target_x = 0 if state == "open" else -self.width
            self._anim = Animation(x=target_x, d=0.2, t="out_cubic")
            self._anim.bind(on_complete=lambda *_: self._finish_state(state))
            self._anim.start(self)
        else:
            self.x = 0 if state == "open" else -self.width
            self._finish_state(state)

    def _finish_state(self, state):
        self._anim = None
        self.state = state
        self.status = "opened" if state == "open" else "closed"

    def on_touch_down(self, touch):
        if self.status == "opened" and self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        if self.status == "opened" and self.close_on_click:
            self.set_state("close", animation=True)
            return True
        return False

    def on_touch_up(self, touch):
        if self.status == "opened" and self.collide_point(*touch.pos):
            return super().on_touch_up(touch)
        return False


class CircleWithText(Widget):
    text = StringProperty("0")
    player = OptionProperty("B", options=["B", "W"])
    min_size = NumericProperty(50)


class BGBoxLayout(BoxLayout, BackgroundMixin):
    pass


# --  gui elements


class KaTrainTextInput(TextInput):
    """TextInput with stub properties for KivyMD compatibility in KV files."""

    helper_text = StringProperty("")
    helper_text_mode = StringProperty("none")
    error = BooleanProperty(False)
    color_mode = StringProperty("primary")
    line_color_focus = ListProperty([1, 1, 1, 1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_active = ""
        if "background_color" not in kwargs:
            self.background_color = Theme.BOX_BACKGROUND_COLOR
        if "foreground_color" not in kwargs:
            self.foreground_color = Theme.INPUT_FONT_COLOR
        if "cursor_color" not in kwargs:
            self.cursor_color = Theme.TEXT_COLOR
        if not getattr(self, "padding", None):
            self.padding = [dp(10), dp(10), dp(10), dp(10)]


class KeyValueSpinner(Spinner):
    __events__ = ["on_select"]
    sync_height_frac = NumericProperty(1.0)
    value_refs = ListProperty()
    selected_index = NumericProperty(0)
    font_name = StringProperty(Theme.DEFAULT_FONT)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.build_values()
        self.bind(size=self.update_dropdown_props, pos=self.update_dropdown_props, value_refs=self.build_values)

    @property
    def input_value(self):
        try:
            return self.value_refs[self.selected_index]
        except KeyError:
            return ""

    @property
    def selected(self):
        try:
            selected = self.selected_index
            return selected, self.value_refs[selected], self.values[selected]
        except (ValueError, IndexError):
            return 0, "", ""

    def on_text(self, _widget, text):
        try:
            new_index = self.values.index(text)
            if new_index != self.selected_index:
                self.selected_index = new_index
                self.dispatch("on_select")
        except (ValueError, IndexError):
            pass

    def on_select(self, *args):
        pass

    def select_key(self, key):
        try:
            ix = self.value_refs.index(key)
            self.text = self.values[ix]
        except (ValueError, IndexError):
            pass

    def build_values(self, *_args):
        if self.value_refs and self.values:
            self.text = self.values[self.selected_index]
            self.font_name = i18n.font_name
            self.update_dropdown_props()

    def update_dropdown_props(self, *largs):
        if not self.sync_height_frac:
            return
        dp = self._dropdown
        if not dp:
            return
        container = dp.container
        if not container:
            return
        h = self.height
        fsz = self.font_size
        for item in container.children[:]:
            item.height = h * self.sync_height_frac
            item.font_size = fsz
            item.font_name = self.font_name


class I18NSpinner(KeyValueSpinner):
    __events__ = ["on_select"]
    sync_height_frac = NumericProperty(1.0)
    value_refs = ListProperty()
    selected_index = NumericProperty(0)
    font_name = StringProperty(Theme.DEFAULT_FONT)

    def build_values(self, *_args):
        self.values = [i18n._(ref) for ref in self.value_refs]
        super().build_values()


class PlayerSetup(BoxLayout):
    player = OptionProperty("B", options=["B", "W"])
    mode = StringProperty("")
    katrain = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.player_subtype_ai.value_refs = AI_STRATEGIES_RECOMMENDED_ORDER
        self.player_subtype_human.value_refs = GAME_TYPES
        self.setup_options()

    def setup_options(self, *_args):
        if self.player_type.selected[1] == self.mode:
            return
        self.mode = self.player_type.selected[1]
        self.update_global_player_info()

    @property
    def player_type_dump(self):
        if self.mode == PLAYER_AI:
            return {"player_type": self.player_type.selected[1], "player_subtype": self.player_subtype_ai.selected[1]}
        else:
            return {
                "player_type": self.player_type.selected[1],
                "player_subtype": self.player_subtype_human.selected[1],
            }

    def update_widget(self, player_type, player_subtype):
        self.player_type.select_key(player_type)  # should trigger setup options
        if self.mode == PLAYER_AI:
            self.player_subtype_ai.select_key(player_subtype)  # should trigger setup options
        else:
            self.player_subtype_human.select_key(player_subtype)  # should trigger setup options

    def update_global_player_info(self):
        if self.parent and self.parent.update_global:
            katrain = self.katrain or getattr(self.parent, "katrain", None)
            if katrain.game and katrain.game.current_node:
                katrain.update_player(self.player, **self.player_type_dump)


class PlayerSetupBlock(BoxLayout):
    players = ObjectProperty(None)
    black = ObjectProperty(None)
    white = ObjectProperty(None)
    update_global = BooleanProperty(False)
    katrain = ObjectProperty(None, allownone=True)
    INSTANCES = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.black = PlayerSetup(player="B")
        self.white = PlayerSetup(player="W")
        self.black.katrain = self.katrain
        self.white.katrain = self.katrain
        self.players = {"B": self.black, "W": self.white}
        self.add_widget(self.black)
        self.add_widget(self.white)
        PlayerSetupBlock.INSTANCES.append(self)

    def on_katrain(self, *_args):
        if self.black:
            self.black.katrain = self.katrain
        if self.white:
            self.white.katrain = self.katrain

    def swap_players(self):
        player_dump = {bw: p.player_type_dump for bw, p in self.players.items()}
        for bw in "BW":
            self.update_player_params(bw, player_dump["B" if bw == "W" else "W"])

    def update_player_params(self, bw, params):
        self.players[bw].update_widget(**params)

    def update_player_info(self, bw, player_info):  # update sub widget based on gui state change
        Clock.schedule_once(
            lambda _dt: self.players[bw].update_widget(
                player_type=player_info.player_type, player_subtype=player_info.player_subtype
            ),
            -1,
        )


class PlayerInfo(BoxLayout, BackgroundMixin):
    captures = ObjectProperty(0)
    player = OptionProperty("B", options=["B", "W"])
    player_type = StringProperty("Player")
    komi = NumericProperty(0)
    player_subtype = StringProperty("")
    name = StringProperty("", allownone=True)
    rank = StringProperty("", allownone=True)
    active = BooleanProperty(True)
    alignment = StringProperty("right")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(player_type=self.set_label, player_subtype=self.set_label, name=self.set_label, rank=self.set_label)

    def set_label(self, *args):
        if not self.subtype_label:  # building
            return
        show_player_name = self.name and self.player_type == PLAYER_HUMAN and self.player_subtype == PLAYING_NORMAL
        if show_player_name:
            text = self.name
        else:
            text = i18n._(self.player_subtype)
        if (
            self.rank
            and self.player_subtype != PLAYING_TEACHING
            and (show_player_name or self.player_type == PLAYER_AI)
        ):
            text += " ({})".format(self.rank)
        self.subtype_label.text = text


class AnalysisToggle(BoxLayout):
    text = StringProperty("")
    default_active = BooleanProperty(False)
    font_name = StringProperty(Theme.DEFAULT_FONT)
    disabled = BooleanProperty(False)
    tri_state = BooleanProperty(False)

    def trigger_action(self, *args, **kwargs):
        return self.checkbox._do_press()

    def activate(self, *_args):
        self.checkbox.active = True

    @property
    def active(self):
        return self.checkbox.active


class MenuItem(LeftButtonBehavior, BoxLayout, BackgroundMixin):
    __events__ = ["on_action", "on_close"]
    icon = StringProperty("")
    text = StringProperty("")
    shortcut = StringProperty("")
    font_name = StringProperty(Theme.DEFAULT_FONT)
    content_width = NumericProperty(100)

    def on_left_release(self):
        self.dispatch("on_close")
        self.dispatch("on_action")

    def on_action(self):
        pass

    def on_close(self):
        pass


class CollapsablePanelHeader(BoxLayout):
    pass


class CollapsablePanelTab(AutoSizedRectangleToggleButton):
    pass


class CollapsablePanel(BoxLayout):
    __events__ = ["on_option_state"]

    options = ListProperty([])
    options_height = NumericProperty(25)
    content_height = NumericProperty(100)
    size_hint_y_open = NumericProperty(None)  # total height inc tabs, overrides content_height
    options_spacing = NumericProperty(6)
    option_labels = ListProperty([])
    option_active = ListProperty([])
    option_colors = ListProperty([])

    contents = ListProperty([])

    closed_label = StringProperty("Closed Panel")

    state = OptionProperty("open", options=["open", "close"])
    close_icon = "Previous-5.png"
    open_icon = "Next-5.png"

    def __init__(self, **kwargs):
        self.open_close_button, self.header = None, None
        self.option_buttons = []
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.bind(
            options=self.build_options,
            option_colors=self.build_options,
            options_height=self.build_options,
            option_active=self.build_options,
            options_spacing=self.build_options,
        )
        self.bind(state=self._on_state, content_height=self._on_size, options_height=self._on_size)
        self.build_options()

    def _on_state(self, *_args):
        self.build()
        self.trigger_select(ix=None)

    def _on_size(self, *_args):
        height, size_hint_y = 1, None
        if self.state == "open" and self.contents:
            if self.size_hint_y_open is not None:
                size_hint_y = self.size_hint_y_open
            else:
                height = self.content_height + self.options_height
        else:
            height = self.header.height
        self.height, self.size_hint_y = height, size_hint_y

    @property
    def option_state(self):
        return {option: active for option, active in zip(self.options, self.option_active)}

    def set_option_state(self, state_dict):
        for ix, (option, button) in enumerate(zip(self.options, self.option_buttons)):
            if option in state_dict:
                self.option_active[ix] = state_dict[option]
                button.state = "down" if state_dict[option] else "normal"
        self.trigger_select(ix=None)

    def build_options(self, *args):
        self.header = CollapsablePanelHeader(
            height=self.options_height, size_hint_y=None, spacing=self.options_spacing, padding=[1, 0, 0, 0]
        )
        self.option_buttons = []
        option_labels = self.option_labels or [i18n._(f"tab:{opt}") for opt in self.options]
        for ix, (lbl, opt_col, active) in enumerate(zip(option_labels, self.option_colors, self.option_active)):
            button = CollapsablePanelTab(
                text=lbl,
                font_name=i18n.font_name,
                active_outline_color=opt_col,
                height=self.options_height,
                state="down" if active else "normal",
            )
            self.option_buttons.append(button)
            button.bind(state=lambda *_args, _ix=ix: self.trigger_select(_ix))
        self.open_close_button = TransparentIconButton(  # <<  / >> collapse button
            icon=self.open_close_icon(),
            icon_size=[0.5 * self.options_height, 0.5 * self.options_height],
            width=0.75 * self.options_height,
            size_hint_x=None,
            on_press=lambda *_args: self.set_state("toggle"),
        )
        self.bind(state=lambda *_args: self.open_close_button.setter("icon")(None, self.open_close_icon()))
        self.build()

    def build(self, *args):
        self.header.clear_widgets()
        if self.state == "open":
            for button in self.option_buttons:
                self.header.add_widget(button)
            self.header.add_widget(Label())  # spacer
        else:
            self.header.add_widget(
                Label(
                    text=i18n._(self.closed_label), font_name=i18n.font_name, halign="right", height=self.options_height
                )
            )
        self.header.add_widget(self.open_close_button)

        super().clear_widgets()
        super().add_widget(self.header)
        if self.state == "open" and self.contents:
            for w in self.contents:
                super().add_widget(w)
        self._on_size()

    def open_close_icon(self):
        return self.open_icon if self.state == "open" else self.close_icon

    def add_widget(self, widget, index=0, **_kwargs):
        self.contents.append(widget)
        self.build()

    def set_state(self, state="toggle"):
        if state == "toggle":
            state = "close" if self.state == "open" else "open"
        self.state = state
        self.build()
        if self.state == "open":
            self.trigger_select(ix=None)

    def trigger_select(self, ix):
        if ix is not None and self.option_buttons:
            self.option_active[ix] = self.option_buttons[ix].state == "down"
        if self.state == "open":
            self.dispatch("on_option_state", {opt: btn.active for opt, btn in zip(self.options, self.option_buttons)})
        return False

    def on_option_state(self, options):
        pass


class StatsBox(BoxLayout, BackgroundMixin):
    winrate = StringProperty("...")
    score = StringProperty("...")
    points_lost = NumericProperty(None, allownone=True)
    player = StringProperty("")


class ClickableLabel(LeftButtonBehavior, Label):
    pass


class ClickableCircle(LeftButtonBehavior, CircleWithText):
    pass


class ScrollableLabel(ScrollView, BackgroundMixin):
    __events__ = ["on_ref_press"]
    outline_color = ListProperty([0, 0, 0, 0])  # mixin not working for some reason
    text = StringProperty("")
    line_height = NumericProperty(1)
    markup = BooleanProperty(False)

    def on_ref_press(self, ref):
        pass


def cached_text_texture(text, font_name, markup, _cache={}, **kwargs):
    args = (text, font_name, markup, *[(k, v) for k, v in kwargs.items()])
    texture = _cache.get(args)
    if texture:
        return texture
    label_cls = CoreMarkupLabel if markup else CoreLabel
    label = label_cls(text=text, bold=True, font_name=font_name or i18n.font_name, **kwargs)
    label.refresh()
    texture = _cache[args] = label.texture
    return texture


def draw_text(pos, text, font_name=None, markup=False, **kwargs):
    texture = cached_text_texture(text, font_name, markup, **kwargs)
    Rectangle(texture=texture, pos=(pos[0] - texture.size[0] / 2, pos[1] - texture.size[1] / 2), size=texture.size)


def draw_circle(pos, r, col):
    Color(*col)
    Ellipse(pos=(pos[0] - r, pos[1] - r), size=(2 * r, 2 * r))


# direct cache to texture, bypassing resource_find
def cached_texture(path, _cache={}):
    tex = _cache.get(path)
    if not tex:
        tex = _cache[path] = Image(resource_find(path)).texture
    return tex
