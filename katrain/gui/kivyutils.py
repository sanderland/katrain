from kivy.clock import Clock
from kivy.core.image import Image
from kivy.core.text import Label as CoreLabel
from kivy.core.text.markup import MarkupLabel as CoreMarkupLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Rectangle
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
from kivymd.app import MDApp
from kivymd.uix.behaviors import CircularRippleBehavior, RectangularRippleBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import BaseFlatButton, BasePressedButton
from kivymd.uix.navigationdrawer import MDNavigationDrawer
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.textfield import MDTextField

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
class SizedButton(LeftButtonBehavior, RectangularRippleBehavior, BasePressedButton, BaseFlatButton, BackgroundMixin):
    text = StringProperty("")
    text_color = ListProperty(Theme.BUTTON_TEXT_COLOR)
    text_size = ListProperty([100, 100])
    halign = OptionProperty("center", options=["left", "center", "right", "justify", "auto"])
    label = ObjectProperty(None)
    padding_x = NumericProperty(6)
    padding_y = NumericProperty(0)
    _font_size = NumericProperty(None)
    font_name = StringProperty(Theme.DEFAULT_FONT)


class AutoSizedButton(SizedButton):
    pass


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


class TransparentIconButton(CircularRippleBehavior, Button):
    color = ListProperty([1, 1, 1, 1])
    icon_size = ListProperty([25, 25])
    icon = StringProperty("")
    disabled = BooleanProperty(False)


class PauseButton(CircularRippleBehavior, LeftButtonBehavior, Widget):
    active = BooleanProperty(True)
    active_line_color = ListProperty([0.5, 0.5, 0.8, 1])
    inactive_line_color = ListProperty([1, 1, 1, 1])
    active_fill_color = ListProperty([0.5, 0.5, 0.5, 1])
    inactive_fill_color = ListProperty([1, 1, 1, 0])
    line_width = NumericProperty(5)
    fill_color = ListProperty([0.5, 0.5, 0.5, 1])
    line_color = ListProperty([0.5, 0.5, 0.5, 1])
    min_size = NumericProperty(100)


# -- basic styles
class LightLabel(Label):
    pass


class StatsLabel(MDBoxLayout):
    text = StringProperty("")
    label = StringProperty("")
    color = ListProperty([1, 1, 1, 1])
    hidden = BooleanProperty(False)
    font_name = StringProperty(Theme.DEFAULT_FONT)


class MyNavigationDrawer(MDNavigationDrawer):
    def on_touch_down(self, touch):
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):  # in PR - closes NavDrawer on any outside click
        if self.status == "opened" and self.close_on_click and not self.collide_point(touch.ox, touch.oy):
            self.set_state("close", animation=True)
            return True
        return super().on_touch_up(touch)


class CircleWithText(Widget):
    text = StringProperty("0")
    player = OptionProperty("B", options=["B", "W"])
    min_size = NumericProperty(50)


class BGBoxLayout(BoxLayout, BackgroundMixin):
    pass


# --  gui elements


class IMETextField(MDTextField):
    _imo_composition = StringProperty("")
    _imo_cursor = ListProperty(None, allownone=True)

    def _bind_keyboard(self):
        super()._bind_keyboard()
        Window.bind(on_textedit=self.window_on_textedit)

    def _unbind_keyboard(self):
        super()._unbind_keyboard()
        Window.unbind(on_textedit=self.window_on_textedit)

    def do_backspace(self, from_undo=False, mode="bkspc"):
        if self._imo_composition == "":  # IMO handles sub-character backspaces
            return super().do_backspace(from_undo, mode)

    def window_on_textedit(self, window, imo_input):
        text_lines = self._lines
        if self._imo_composition:
            pcc, pcr = self._imo_cursor
            text = text_lines[pcr]
            if text[pcc - len(self._imo_composition) : pcc] == self._imo_composition:  # should always be true
                remove_old_imo_text = text[: pcc - len(self._imo_composition)] + text[pcc:]
                ci = self.cursor_index()
                self._refresh_text_from_property("insert", *self._get_line_from_cursor(pcr, remove_old_imo_text))
                self.cursor = self.get_cursor_from_index(ci - len(self._imo_composition))

        if imo_input:
            if self._selection:
                self.delete_selection()
            cc, cr = self.cursor
            text = text_lines[cr]
            new_text = text[:cc] + imo_input + text[cc:]
            self._refresh_text_from_property("insert", *self._get_line_from_cursor(cr, new_text))
            self.cursor = self.get_cursor_from_index(self.cursor_index() + len(imo_input))
        self._imo_composition = imo_input
        self._imo_cursor = self.cursor


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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        MDApp.get_running_app().bind(language=self.build_values)

    def build_values(self, *_args):
        self.values = [i18n._(ref) for ref in self.value_refs]
        super().build_values()


class PlayerSetup(MDBoxLayout):
    player = OptionProperty("B", options=["B", "W"])
    mode = StringProperty("")

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
            katrain = MDApp.get_running_app().gui
            if katrain.game and katrain.game.current_node:
                katrain.update_player(self.player, **self.player_type_dump)


class PlayerSetupBlock(MDBoxLayout):
    players = ObjectProperty(None)
    black = ObjectProperty(None)
    white = ObjectProperty(None)
    update_global = BooleanProperty(False)
    INSTANCES = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.black = PlayerSetup(player="B")
        self.white = PlayerSetup(player="W")
        self.players = {"B": self.black, "W": self.white}
        self.add_widget(self.black)
        self.add_widget(self.white)
        PlayerSetupBlock.INSTANCES.append(self)

    def swap_players(self):
        player_dump = {bw: p.player_type_dump for bw, p in self.players.items()}
        for bw in "BW":
            self.update_player_params(bw, player_dump["B" if bw == "W" else "W"])

    def update_player_params(self, bw, params):
        self.players[bw].update_widget(**params)

    def update_player_info(self, bw, player_info):  # update sub widget based on gui state change
        self.players[bw].update_widget(player_type=player_info.player_type, player_subtype=player_info.player_subtype)


class PlayerInfo(MDBoxLayout, BackgroundMixin):
    captures = NumericProperty(0)
    player = OptionProperty("B", options=["B", "W"])
    player_type = StringProperty("Player")
    komi = NumericProperty(0)
    player_subtype = StringProperty("")
    name = StringProperty("", allownone=True)
    rank = StringProperty("", allownone=True)
    active = BooleanProperty(True)

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


class TimerOrMoveTree(MDBoxLayout):
    mode = StringProperty(MODE_PLAY)


class Timer(BGBoxLayout):
    state = ListProperty([30, 5, 1])
    timeout = BooleanProperty(False)


class TriStateMDCheckbox(MDCheckbox):
    tri_state = BooleanProperty(False)
    slashed = BooleanProperty(False)
    checkbox_icon_slashed = StringProperty("checkbox-blank-off-outline")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(slashed=self.update_icon)

    def _do_press(self):
        if not self.tri_state:
            return super()._do_press()
        if self.slashed:
            self.state = "normal"
            self.slashed = False
        elif self.state == "down":
            self.state = "normal"
            self.slashed = True
        else:
            self.state = "down"
            self.slashed = False
        self.update_icon()

    def update_icon(self, *args):
        if self.tri_state and self.slashed:
            self.icon = self.checkbox_icon_slashed
        elif self.state == "down":
            self.icon = self.checkbox_icon_down
        else:
            self.icon = self.checkbox_icon_normal


class AnalysisToggle(MDBoxLayout):
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


class MenuItem(RectangularRippleBehavior, LeftButtonBehavior, MDBoxLayout, BackgroundMixin):
    __events__ = ["on_action", "on_close"]
    icon = StringProperty("")
    text = StringProperty("")
    shortcut = StringProperty("")
    font_name = StringProperty(Theme.DEFAULT_FONT)
    content_width = NumericProperty(100)

    def on_left_release(self):
        self.anim_complete()  # kill ripple
        self.dispatch("on_close")
        self.dispatch("on_action")

    def on_action(self):
        pass

    def on_close(self):
        pass


class CollapsablePanelHeader(MDBoxLayout):
    pass


class CollapsablePanelTab(AutoSizedRectangleToggleButton):
    pass


class CollapsablePanel(MDBoxLayout):
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
        MDApp.get_running_app().bind(language=lambda *_: Clock.schedule_once(self.build_options, 0))
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


class StatsBox(MDBoxLayout, BackgroundMixin):
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
