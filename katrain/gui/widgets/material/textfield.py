"""Material Design style single-line text field.

A :class:`~kivy.uix.textinput.TextInput` with the three decorations Material
Design puts around it: an underline that lights up while the field has focus, a
hint that floats up out of the way once there is text, and an optional line of
helper text underneath.
"""

from kivy.animation import Animation
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ColorProperty, NumericProperty, OptionProperty, StringProperty
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

HINT_RESTING_Y = dp(38)  # hint sits over the text while the field is empty and unfocused
HINT_FLOATING_Y = dp(14)  # ... and floats up to here once it is focused or filled
HINT_RESTING_FONT_SIZE = sp(16)
HINT_FLOATING_FONT_SIZE = sp(12)
HELPER_FONT_SIZE = sp(12)
ANIMATION_DURATION = 0.2

# `Clear` drops TextInput's own background, cursor and text color instructions, so this rule
# has to draw the decorations *and* put the cursor and text color back.
Builder.load_string(
    """
#:import Theme katrain.gui.theme.Theme

<MaterialTextField>:
    line_color_normal: Theme.INPUT_LINE_COLOR
    line_color_focus: Theme.INPUT_FONT_COLOR
    error_color: Theme.INPUT_ERROR_COLOR
    hint_color: Theme.INPUT_HINT_COLOR
    foreground_color: Theme.INPUT_FONT_COLOR
    font_size: sp(16)
    multiline: False
    size_hint_y: None
    height: self.minimum_height + dp(8)
    padding: 0, dp(16), 0, dp(10)
    canvas.before:
        Clear
        Color:  # resting underline, dashed while disabled
            rgba: root.line_color_normal
        Line:
            points: self.x, self.y + dp(16), self.right, self.y + dp(16)
            width: 1
            dash_length: dp(3)
            dash_offset: 2 if self.disabled else 0
        Color:  # underline that grows out from the center when the field takes focus
            rgba: root._line_color
        Rectangle:
            size: root._line_width, dp(2)
            pos: self.center_x - root._line_width / 2, self.y + dp(16)
        Color:
            rgba: root._hint_color
        Rectangle:
            texture: root._hint_label.texture
            size: root._hint_label.texture_size
            pos: self.x, self.top - root._hint_y
        Color:
            rgba: root._helper_color
        Rectangle:
            texture: root._helper_label.texture
            size: root._helper_label.texture_size
            pos: self.x, self.y
        Color:  # cursor
            rgba:
                (self.cursor_color
                if self.focus and not self._cursor_blink
                and int(self.x + self.padding[0]) <= self._cursor_visual_pos[0] <= int(self.right - self.padding[2])
                else (0, 0, 0, 0))
        Rectangle:
            pos: self._cursor_visual_pos
            size: self.cursor_width, -self._cursor_visual_height
        Color:  # colour the text itself is drawn in
            rgba:
                (self.disabled_foreground_color if self.disabled
                else (root.error_color if root.error else self.foreground_color))
"""
)


class MaterialTextField(TextInput):
    hint_text = StringProperty("")  # shadows TextInput's, which we render ourselves
    helper_text = StringProperty("")
    helper_text_mode = OptionProperty("none", options=["none", "on_error", "on_focus", "persistent"])
    error = BooleanProperty(False)

    line_color_normal = ColorProperty([1, 1, 1, 0.12])
    line_color_focus = ColorProperty([1, 1, 1, 1])
    error_color = ColorProperty([0.84, 0, 0, 1])
    hint_color = ColorProperty([1, 1, 1, 0.5])

    _hint_y = NumericProperty(HINT_RESTING_Y)
    _line_width = NumericProperty(0)
    _line_color = ColorProperty([0, 0, 0, 0])
    _hint_color = ColorProperty([0, 0, 0, 0])
    _helper_color = ColorProperty([0, 0, 0, 0])
    _hint_font_size = NumericProperty(HINT_RESTING_FONT_SIZE)

    def __init__(self, **kwargs):
        self._hint_label = Label(font_size=HINT_RESTING_FONT_SIZE, halign="left", valign="middle")
        self._helper_label = Label(font_size=HELPER_FONT_SIZE, halign="left", valign="middle")
        super().__init__(**kwargs)
        self.bind(
            hint_text=self._hint_label.setter("text"),
            helper_text=self._helper_label.setter("text"),
            _hint_font_size=self._hint_label.setter("font_size"),
            font_name=self._on_font_name,
            error=self._refresh_decorations,
            helper_text_mode=self._refresh_decorations,
            line_color_focus=self._refresh_decorations,
            width=self._refresh_decorations,
        )
        self._hint_label.text = self.hint_text
        self._helper_label.text = self.helper_text
        self._on_font_name(self, self.font_name)
        self._refresh_decorations(animate=False)

    def _refresh_hint_text(self):
        """Suppress TextInput's own hint rendering; this class draws a floating one instead."""

    def on_focus(self, *_args):
        self._refresh_decorations()

    def on_text(self, *_args):
        self._refresh_decorations()

    def _on_font_name(self, _instance, font_name):
        self._hint_label.font_name = font_name
        self._helper_label.font_name = font_name

    def _refresh_decorations(self, *_args, animate=True):
        """Animate underline, hint and helper text to match the current state."""
        floating = bool(self.focus or self.text)
        targets = {
            "_hint_y": HINT_FLOATING_Y if floating else HINT_RESTING_Y,
            "_hint_font_size": HINT_FLOATING_FONT_SIZE if floating else HINT_RESTING_FONT_SIZE,
            "_line_width": self.width if (self.focus or self.error) else 0,
            "_line_color": self.error_color if self.error else self.line_color_focus,
            "_hint_color": self._target_hint_color(),
            "_helper_color": self._target_helper_color(),
        }
        Animation.cancel_all(self, *targets)
        if animate:
            Animation(duration=ANIMATION_DURATION, t="out_quad", **targets).start(self)
        else:
            for name, value in targets.items():
                setattr(self, name, value)

    def _target_hint_color(self):
        if self.error:
            return self.error_color
        return self.line_color_focus if self.focus else self.hint_color

    def _target_helper_color(self):
        shown = {"none": False, "on_error": self.error, "on_focus": self.focus, "persistent": True}
        if not shown[self.helper_text_mode]:
            return [0, 0, 0, 0]
        return self.error_color if self.error else self.hint_color
