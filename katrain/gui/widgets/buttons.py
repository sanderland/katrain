"""Buttons.

The `Sized*` family are all the same widget with different `.kv` rules; the name
says how each one sizes itself and what it draws:

* `Sized...` takes its size from the layout, `AutoSized...` from its label's text.
* `...RectangleButton` draws an outline, `...RoundedRectangleButton` a rounded one
  (both defined in `gui.kv`), and a plain `SizedButton` neither.
* `...ToggleButton` stays down when pressed, with separate colours per state.
"""

from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    ObjectProperty,
    OptionProperty,
    StringProperty,
)
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ToggleButtonBehavior
from kivy.uix.button import Button
from kivy.uix.widget import Widget

from katrain.gui.theme import Theme
from katrain.gui.widgets.base import BackgroundMixin, LeftButtonBehavior
from katrain.gui.widgets.material import CircularRippleBehavior, RectangularRippleBehavior


class SizedButton(RectangularRippleBehavior, LeftButtonBehavior, AnchorLayout, BackgroundMixin):
    text = StringProperty("")
    text_color = ListProperty(Theme.BUTTON_TEXT_COLOR)
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
    """Button showing only an image, with no background of its own."""

    color = ListProperty([1, 1, 1, 1])
    icon_size = ListProperty([25, 25])
    icon = StringProperty("")


class PauseButton(CircularRippleBehavior, LeftButtonBehavior, Widget):
    """Circled pause symbol for the game clock; drawn by the `<PauseButton>` rule in `gui.kv`."""

    active = BooleanProperty(True)
    active_line_color = ListProperty([0.5, 0.5, 0.8, 1])
    inactive_line_color = ListProperty([1, 1, 1, 1])
    active_fill_color = ListProperty([0.5, 0.5, 0.5, 1])
    inactive_fill_color = ListProperty([1, 1, 1, 0])
    line_width = NumericProperty(5)
    fill_color = ListProperty([0.5, 0.5, 0.5, 1])
    line_color = ListProperty([0.5, 0.5, 0.5, 1])
    min_size = NumericProperty(100)
