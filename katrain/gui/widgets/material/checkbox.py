"""Material Design style check box, drawn with canvas instructions."""

from kivy.animation import Animation
from kivy.lang import Builder
from kivy.metrics import sp
from kivy.properties import BooleanProperty, ColorProperty, NumericProperty
from kivy.uix.behaviors import ToggleButtonBehavior
from kivy.uix.widget import Widget

from katrain.gui.widgets.material.ripple import CircularRippleBehavior

Builder.load_string(
    """
#:import Theme katrain.gui.theme.Theme

<MaterialCheckBox>:
    selected_color: Theme.CHECKBOX_SELECTED_COLOR
    unselected_color: Theme.CHECKBOX_UNSELECTED_COLOR
    disabled_color: Theme.CHECKBOX_DISABLED_COLOR
    color: self.disabled_color if self.disabled else (self.selected_color if self.active else self.unselected_color)
    canvas:
        Color:
            rgba: root.color
        SmoothLine:  # the box
            rounded_rectangle:
                (self.center_x - root._drawn_size / 2,
                self.center_y - root._drawn_size / 2,
                root._drawn_size, root._drawn_size, root._drawn_size / 9)
            width: max(0.01, root._drawn_size / 21)
        Color:  # the tick, only visible when checked
            rgba: root.color if root.active else [0, 0, 0, 0]
        SmoothLine:
            points:
                (self.center_x - root._drawn_size * 0.28, self.center_y + root._drawn_size * 0.02,
                self.center_x - root._drawn_size * 0.08, self.center_y - root._drawn_size * 0.20,
                self.center_x + root._drawn_size * 0.30, self.center_y + root._drawn_size * 0.22)
            width: max(0.01, root._drawn_size / 21)
            cap: 'round'
            joint: 'round'
"""
)


class MaterialCheckBox(CircularRippleBehavior, ToggleButtonBehavior, Widget):
    """Check box with the outlined-square-plus-tick look of Material Design.

    The box is drawn at a fixed :attr:`box_size`, centred in the widget, so it
    keeps its proportions whatever size the surrounding layout gives it.
    """

    active = BooleanProperty(False)
    box_size = NumericProperty(sp(16))

    selected_color = ColorProperty([1, 1, 1, 1])
    unselected_color = ColorProperty([1, 1, 1, 0.7])
    disabled_color = ColorProperty([1, 1, 1, 0.12])
    color = ColorProperty([1, 1, 1, 0.7])

    _drawn_size = NumericProperty(sp(16))  # animated to give the box a small "pop" when toggled

    def on_state(self, _instance, state):
        self.active = state == "down"
        grow = Animation(_drawn_size=self.box_size, duration=0.1, t="out_quad")
        shrink = Animation(_drawn_size=0, duration=0.1, t="out_quad")
        shrink.bind(on_complete=lambda *_args: grow.start(self))
        Animation.cancel_all(self, "_drawn_size")
        shrink.start(self)

    def on_active(self, _instance, active):
        self.state = "down" if active else "normal"

    def on_box_size(self, _instance, box_size):
        self._drawn_size = box_size
