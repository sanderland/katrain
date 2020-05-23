import json
import random
import re

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import *
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty, OptionProperty, ObjectProperty
from kivy.uix.behaviors import ToggleButtonBehavior, ButtonBehavior
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget


# --new
from kivymd.app import MDApp
from kivymd.uix.behaviors import RectangularRippleBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import BasePressedButton, BaseFlatButton
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.navigationdrawer import MDNavigationDrawer

# --- new mixins
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
class SizedMDBaseButton(BasePressedButton, BaseFlatButton, LeftButtonBehavior):  # avoid baserectangular for sizing
    text = StringProperty("")
    halign = OptionProperty("center", options=["left", "center", "right", "justify", "auto"])
    label = ObjectProperty(None)
    height = NumericProperty(33)

class SizedMDFlatButton(RectangularRippleBehavior, SizedMDBaseButton):
    pass


class SizedMDFlatRectangleButton(SizedMDFlatButton, OutlineColor):
    color = ListProperty([1, 1, 1, 1])


class SizedMDFlatRectangleToggleButton(SizedMDFlatRectangleButton, ToggleButtonBehavior):
    inactive_color = ListProperty([0.5, 0.5, 0.5, 1])

    @property
    def active(self):
        return self.state == "down"


class AutoSizedMDFlatRectangleToggleButton(SizedMDFlatRectangleToggleButton):
    hor_padding = NumericProperty(3)


# -- basic styles
class LightLabel(MDLabel):
    pass


class BackgroundLabel(MDLabel, BackgroundColor):
    pass


class CensorableLabel(MDBoxLayout):
    text = StringProperty("")
    label = StringProperty("")
    color = ListProperty([1, 1, 1, 1])


class MyNavigationDrawer(MDNavigationDrawer):  # in PR
    def on_touch_down(self, touch):
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if self.status == "opened" and self.close_on_click and not self.collide_point(touch.ox, touch.oy):
            self.set_state("close", animation=True)
            return True
        return super().on_touch_up(touch)


class CircleWithText(MDFloatLayout):
    text = StringProperty("0")
    player = OptionProperty("Black", options=["Black", "White"])
    min_size = NumericProperty(50)


# -- gui elements


class MainMenuItem(RectangularRippleBehavior, LeftButtonBehavior, MDBoxLayout):
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


class CollapsablePanel(MDBoxLayout):
    __events__ = ["on_option_select"]
    options = ListProperty([])
    options_height = NumericProperty(25)
    option_active = ListProperty([])
    option_colors = ListProperty([])

    def __init__(self, **kwargs):
        self.contents = None
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.bind(options=self.build, option_colors=self.build, options_height=self.build, option_active=self.build)

    def build(self, *args, **kwargs):
        print(args, kwargs, "b")
        self.clear_widgets()
        header = MDBoxLayout(adaptive_height=True, padding=[4, 0, 0, 0],spacing=2)
        option_colors = self.option_colors
        for opt, opt_col, active in zip(self.options, option_colors, self.option_active):
            header.add_widget(AutoSizedMDFlatRectangleToggleButton(text=opt, color=opt_col,
                                                                   height=self.options_height,
                                                                   on_press=lambda _:print(self.size,_.size),
                                                                   state="down" if active else "normal"))
        header.add_widget(SizedMDFlatRectangleButton(text="x",height=self.options_height))
        super().add_widget(header)
        if self.contents:
            super().add_widget(self.contents)

    def add_widget(self, widget, index=0, **_kwargs):
        if self.contents:
            raise ValueError("CollapsablePanel can only have one child")
        self.contents = widget
        self.build()

    def on_option_select(self, states):
        pass


# --- not checked


class ToolTipLabel(MDLabel):
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


class ClickableLabel(LightLabel, LeftButtonBehavior):
    pass


class LightHelpLabel(ScaledLightLabel):
    pass


class ScrollableLabel(ScrollView, BackgroundColor, OutlineColor):
    __events__ = ["on_ref_press"]
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


class LabelledTextInput(TextInput):
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
    label = CoreLabel(text=text, bold=True, **kw)
    label.refresh()
    Rectangle(texture=label.texture, pos=(pos[0] - label.texture.size[0] / 2, pos[1] - label.texture.size[1] / 2), size=label.texture.size)


def draw_circle(pos, r, col):
    Color(*col)
    Ellipse(pos=(pos[0] - r, pos[1] - r), size=(2 * r, 2 * r))
