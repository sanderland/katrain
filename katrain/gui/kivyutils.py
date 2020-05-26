import json
import random
import re

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import *
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty, OptionProperty, ObjectProperty
from kivy.uix.behaviors import ToggleButtonBehavior, ButtonBehavior
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget


# --new
from kivymd.app import MDApp
from kivymd.uix.behaviors import RectangularRippleBehavior, CircularRippleBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import BasePressedButton, BaseFlatButton
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.navigationdrawer import MDNavigationDrawer
from kivy.core.text import Label as CoreLabel
from katrain.core.utils import i18n, I18NTextInput, I18NLabel

#

# --- new mixins
from katrain.gui.style import WHITE


class BackgroundColor(Widget):
    background_color = ListProperty([1, 1, 1, 0])


class OutlineColor(Widget):
    outline_color = ListProperty([1, 1, 1, 0])
    outline_width = NumericProperty(1)


class LeftButtonBehavior(ButtonBehavior):  # stops buttons etc activating on right click
    def __init__(self, **kwargs):
        self.register_event_type("on_left_release")
        self.register_event_type("on_left_press")
        super().__init__(**kwargs)

    def on_touch_down(self, touch):
        return super().on_touch_down(touch)

    def on_release(self):
        if not self.last_touch or self.last_touch.button == "left":
            self.dispatch("on_left_release")
        return super().on_release()

    def on_press(self):
        if not self.last_touch or self.last_touch.button == "left":
            self.dispatch("on_left_press")
        return super().on_press()

    def on_left_release(self):
        pass

    def on_left_press(self):
        pass


# -- resizeable buttons
class SizedMDButton(LeftButtonBehavior, RectangularRippleBehavior, BasePressedButton, BaseFlatButton, BackgroundColor, OutlineColor):  # avoid baserectangular for sizing
    text = StringProperty("")
    text_color = ListProperty(WHITE)
    halign = OptionProperty("center", options=["left", "center", "right", "justify", "auto"])
    label = ObjectProperty(None)
    height = NumericProperty(33)


class SizedMDToggleButton(ToggleButtonBehavior, SizedMDButton):
    inactive_outline_color = ListProperty([0.5, 0.5, 0.5, 0])
    active_outline_color = ListProperty([1, 1, 1, 0])
    inactive_background_color = ListProperty([0.5, 0.5, 0.5, 1])
    active_background_color = ListProperty([1, 1, 1, 1])


class SizedMDRectangleButton(SizedMDButton):
    pass


class SizedMDRectangleToggleButton(SizedMDToggleButton):
    pass


class AutoSizedMDRectangleButton(SizedMDRectangleButton):
    hor_padding = NumericProperty(6)


class AutoSizedMDRectangleToggleButton(SizedMDRectangleToggleButton):
    hor_padding = NumericProperty(6)


class TransparentIconButton(CircularRippleBehavior, Button):
    icon_size = ListProperty([25, 25])
    icon = StringProperty("")


# -- basic styles
class LightLabel(I18NLabel):
    pass


class StatsLabel(MDBoxLayout):
    text = StringProperty("")
    label = StringProperty("")
    color = ListProperty([1, 1, 1, 1])
    hidden = BooleanProperty(False)


class MyNavigationDrawer(MDNavigationDrawer):  # in PR - closes NavDrawer on any outside click
    def on_touch_down(self, touch):
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if self.status == "opened" and self.close_on_click and not self.collide_point(touch.ox, touch.oy):
            self.set_state("close", animation=True)
            return True
        return super().on_touch_up(touch)


class CircleWithText(Widget):
    text = StringProperty("0")
    player = OptionProperty("Black", options=["Black", "White"])
    min_size = NumericProperty(50)


# -- new gui elements


class PlayerInfo(MDBoxLayout, BackgroundColor, OutlineColor):
    captures = NumericProperty(0)
    player = OptionProperty("Black", options=["Black", "White"])
    player_type = StringProperty("Player")
    player_subtype = StringProperty("")
    active = BooleanProperty(True)


class AnalysisToggle(MDBoxLayout):
    text = StringProperty("")
    active = BooleanProperty(False)


class MainMenuItem(RectangularRippleBehavior, LeftButtonBehavior, MDBoxLayout, BackgroundColor):
    __events__ = ["on_action"]
    icon = StringProperty("")
    text = StringProperty("")
    shortcut = StringProperty("")

    def on_left_release(self):
        self.anim_complete()  # kill ripple
        MDApp.get_running_app().gui.nav_drawer.set_state("close")
        self.dispatch("on_action")

    def on_action(self):
        pass


class CollapsablePanelHeader(MDBoxLayout):
    pass


class CollapsablePanelTab(AutoSizedMDRectangleToggleButton):
    pass


class CollapsablePanel(MDBoxLayout):
    __events__ = ["on_option_state"]

    options = ListProperty([])
    options_height = NumericProperty(25)
    options_spacing = NumericProperty(6)
    option_labels = ListProperty([])
    option_default_active = ListProperty([])
    option_colors = ListProperty([])
    closed_label = StringProperty("Closed Panel")

    size_hint_y_open = NumericProperty(1)
    height_open = NumericProperty(None)

    state = OptionProperty("open", options=["open", "close"])
    close_icon = "img/flaticon/previous5.png"
    open_icon = "img/flaticon/next5.png"

    def __init__(self, **kwargs):
        self.header, self.contents, self.open_close_button = None, None, None
        self.option_buttons = []
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.bind(
            options=self.build_options,
            option_colors=self.build_options,
            options_height=self.build_options,
            option_default_active=self.build_options,
            options_spacing=self.build_options,
        )
        self.bind(state=self.build, size_hint_y_open=self.build, height_open=self.build)
        self.build_options()

    def build_options(self, *args, **kwargs):
        self.header = CollapsablePanelHeader(height=self.options_height, size_hint_y=None, spacing=self.options_spacing, padding=[1, 0, 0, 0])
        self.option_buttons = []
        option_labels = self.option_labels or [i18n._(f"tab:{opt}") for opt in self.options]
        for lbl, opt_col, active in zip(option_labels, self.option_colors, self.option_default_active):
            button = CollapsablePanelTab(text=lbl, active_outline_color=opt_col, height=self.options_height, on_press=self.trigger_select, state="down" if active else "normal")
            self.option_buttons.append(button)
        self.open_close_button = TransparentIconButton(  # <<  / >> collapse button
            icon=self.open_close_icon(),
            icon_size=[0.5 * self.options_height, 0.5 * self.options_height],
            width=0.75 * self.options_height,
            size_hint_x=None,
            on_press=lambda *_args: self.set_state("toggle"),
        )
        self.bind(state=lambda *_args: self.open_close_button.setter("icon")(None, self.open_close_icon()))
        self.build()

    def build(self, *args, **kwargs):
        self.header.clear_widgets()
        if self.state == "open":
            for button in self.option_buttons:
                self.header.add_widget(button)
            self.header.add_widget(Label())  # spacer
            self.trigger_select()
        else:
            self.header.add_widget(I18NLabel(text=i18n._(self.closed_label), halign="right", height=self.options_height))
        self.header.add_widget(self.open_close_button)

        super().clear_widgets()
        super().add_widget(self.header)
        height, size_hint_y = 1, None
        if self.state == "open" and self.contents:
            super().add_widget(self.contents)
            if self.height_open:
                height = self.height_open
            else:
                size_hint_y = self.size_hint_y_open
        else:
            height = self.header.height
        self.height, self.size_hint_y = height, size_hint_y

    def open_close_icon(self):
        return self.open_icon if self.state == "open" else self.close_icon

    def add_widget(self, widget, index=0, **_kwargs):
        if self.contents:
            raise ValueError("CollapsablePanel can only have one child")
        self.contents = widget
        self.build()

    def set_state(self, state="toggle"):
        if state == "toggle":
            state = "close" if self.state == "open" else "open"
        self.state = state
        self.build()
        if self.state == "open":
            self.trigger_select()

    def trigger_select(self, *_args):
        if self.state == "open":
            self.dispatch("on_option_state", {opt: btn.state == "down" for opt, btn in zip(self.options, self.option_buttons)})

    def on_option_state(self, options):
        pass


class StatsBox(MDBoxLayout, BackgroundColor):
    winrate = StringProperty("...")
    score = StringProperty("...")
    points_lost = NumericProperty(None, allownone=True)
    player = StringProperty("")


# --- not checked


class ToolTipLabel(I18NLabel):
    pass


class ToolTipBehavior(object):  # TODO restyle
    tooltip_text = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tooltip = ToolTipLabel()
        self.open = False

    def on_touch_up(self, touch):
        inside = self.collide_point(*self.to_widget(*touch.pos))
        if inside and touch.button == "right" and self.tooltip_text:
            if not self.open:
                self.display_tooltip(touch.pos)
            Clock.schedule_once(lambda _: self.set_position(touch.pos), 0)
        elif not inside and self.open:
            self.close_tooltip()
        return super().on_touch_up(touch)

    def close_tooltip(self):
        self.open = False
        Window.remove_widget(self.tooltip)

    def on_size(self, *args):
        mid = (self.pos[0] + self.width / 2, self.pos[1] + self.height / 2)
        self.set_position(mid)

    def set_position(self, pos):
        self.tooltip.pos = (pos[0] - self.tooltip.texture_size[0], pos[1])

    def display_tooltip(self, pos):
        self.open = True
        self.tooltip.text = self.tooltip_text
        Window.add_widget(self.tooltip)


class ScaledLightLabel(LightLabel, ToolTipBehavior):
    num_lines = NumericProperty(1)


class ClickableLabel(LeftButtonBehavior, I18NLabel):
    pass


class LightHelpLabel(ScaledLightLabel):
    pass


class ScrollableLabel(ScrollView, BackgroundColor):
    __events__ = ["on_ref_press"]
    outline_color = ListProperty([0, 0, 0, 0])  # mixin not working for some reason
    text = StringProperty("")
    markup = BooleanProperty(False)

    def on_ref_press(self, ref):
        pass


class StyledButton(Button, LeftButtonBehavior, ToolTipBehavior):
    button_color = ListProperty([])
    button_color_down = ListProperty([])
    radius = ListProperty((0,))


class StyledToggleButton(StyledButton, ToggleButtonBehavior, ToolTipBehavior):
    value = StringProperty("")
    allow_no_selection = BooleanProperty(False)

    def _do_press(self):
        if (self.last_touch and self.last_touch.button != "left") or (not self.allow_no_selection and self.state == "down"):
            return
        self._release_group(self)
        self.state = "normal" if self.state == "down" else "down"


class StyledSpinner(Spinner):
    sync_height_frac = NumericProperty(1.0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(size=self._update_dropdown_size_frac, pos=self._update_dropdown_size_frac)

    def _update_dropdown_size_frac(self, *largs):
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


class ToggleButtonContainer(GridLayout):
    __events__ = ("on_selection",)

    options = ListProperty([])
    labels = ListProperty([])
    tooltips = ListProperty(None)
    selected = StringProperty("")
    group = StringProperty(None)
    autosize = BooleanProperty(True)
    spacing = ListProperty((1, 1))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rows = 1
        self.cols = len(self.options)
        Clock.schedule_once(self._build, 0)

    def on_selection(self, *args):
        pass

    def _build(self, _dt):
        self.cols = len(self.options)
        self.group = self.group or str(random.random())
        if not self.selected and self.options:
            self.selected = self.options[0]
        if len(self.labels) < len(self.options):
            self.labels += self.options[len(self.labels) + 1 :]

        def state_handler(*args):
            self.dispatch("on_selection")

        for i, opt in enumerate(self.options):
            state = "down" if opt == self.selected else "normal"
            tooltip = self.tooltips[i] if self.tooltips else None
            self.add_widget(StyledToggleButton(group=self.group, text=self.labels[i], value=opt, state=state, on_press=state_handler, tooltip_text=tooltip))
        Clock.schedule_once(self._size, 0)

    def _size(self, _dt):
        if self.autosize:
            for tb in self.children:
                tb.size_hint = (tb.texture_size[0] + 10, 1)

    @property
    def value(self):
        for tb in self.children:
            if tb.state == "down":
                return tb.value
        if self.options:
            return self.options[0]


class LabelledTextInput(I18NTextInput):
    input_property = StringProperty("")
    multiline = BooleanProperty(False)

    @property
    def input_value(self):
        return self.text


class LabelledObjectInputArea(LabelledTextInput):
    multiline = BooleanProperty(True)

    @property
    def input_value(self):
        return json.loads(self.text.replace("'", '"').replace("True", "true").replace("False", "false"))


class LabelledCheckBox(CheckBox):
    input_property = StringProperty("")

    def __init__(self, text=None, **kwargs):
        if text is not None:
            kwargs["active"] = text.lower() == "true"
        super().__init__(**kwargs)

    @property
    def input_value(self):
        return bool(self.active)


class LabelledSpinner(StyledSpinner):
    input_property = StringProperty("")

    @property
    def input_value(self):
        return self.text


class LabelledFloatInput(LabelledTextInput):
    signed = BooleanProperty(True)
    pat = re.compile("[^0-9-]")

    def insert_text(self, substring, from_undo=False):
        pat = self.pat
        if "." in self.text:
            s = re.sub(pat, "", substring)
        else:
            s = ".".join([re.sub(pat, "", s) for s in substring.split(".", 1)])
        r = super().insert_text(s, from_undo=from_undo)
        if not self.signed and "-" in self.text:
            self.text = self.text.replace("-", "")
        elif self.text and "-" in self.text[1:]:
            self.text = self.text[0] + self.text[1:].replace("-", "")
        return r

    @property
    def input_value(self):
        return float(self.text)


class LabelledIntInput(LabelledTextInput):
    pat = re.compile("[^0-9]")

    def insert_text(self, substring, from_undo=False):
        return super().insert_text(re.sub(self.pat, "", substring), from_undo=from_undo)

    @property
    def input_value(self):
        return int(self.text)


def draw_text(pos, text, **kw):
    label = CoreLabel(text=text, bold=True, font_name=i18n._("Roboto"), **kw)  #
    label.refresh()
    Rectangle(texture=label.texture, pos=(pos[0] - label.texture.size[0] / 2, pos[1] - label.texture.size[1] / 2), size=label.texture.size)


def draw_circle(pos, r, col):
    Color(*col)
    Ellipse(pos=(pos[0] - r, pos[1] - r), size=(2 * r, 2 * r))
