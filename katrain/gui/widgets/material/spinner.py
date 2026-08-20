"""Material Design indeterminate progress indicator: a spinning, stretching arc."""

from kivy.animation import Animation
from kivy.lang import Builder
from kivy.properties import BooleanProperty, ColorProperty, NumericProperty
from kivy.uix.widget import Widget

ARC_MIN_SPAN = 8  # degrees; the arc never fully closes up
ARC_MAX_SPAN = 278  # ARC_MIN_SPAN + 270, the widest the arc opens
SWEEP_TIME = 0.6  # seconds for one open or close of the arc
ROTATION_TIME = 2  # seconds for one full turn

Builder.load_string(
    """
<LoadingSpinner>:
    canvas.before:
        PushMatrix
        Rotate:
            angle: self._rotation
            origin: self.center
    canvas:
        Color:
            rgba: self.color
        SmoothLine:
            circle: self.center_x, self.center_y, self.width / 2, self._angle_start, self._angle_end
            cap: 'square'
            width: dp(2.25)
    canvas.after:
        PopMatrix
"""
)


class LoadingSpinner(Widget):
    active = BooleanProperty(True)
    color = ColorProperty([1, 1, 1, 1])

    _rotation = NumericProperty(0)
    _angle_start = NumericProperty(0)
    _angle_end = NumericProperty(ARC_MIN_SPAN)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.on_active(self, self.active)

    def on_active(self, _instance, active):
        if active:
            self._spin()
            self._sweep_open()
        else:
            Animation.cancel_all(self, "_rotation", "_angle_start", "_angle_end")
            self._angle_start, self._angle_end = 0, ARC_MIN_SPAN

    def _spin(self):
        """Turn the whole arc a full circle, restarting for as long as we are active."""
        anim = Animation(_rotation=self._rotation - 360, duration=ROTATION_TIME, t="linear")
        anim.bind(on_complete=lambda *_args: self.active and self._spin())
        anim.start(self)

    def _sweep_open(self):
        """Grow the arc by dragging its end forward, then close it by catching up with the start."""
        anim = Animation(_angle_end=self._angle_start + ARC_MAX_SPAN, duration=SWEEP_TIME, t="in_out_cubic")
        anim.bind(on_complete=lambda *_args: self.active and self._sweep_closed())
        anim.start(self)

    def _sweep_closed(self):
        anim = Animation(_angle_start=self._angle_end - ARC_MIN_SPAN, duration=SWEEP_TIME, t="in_out_cubic")
        anim.bind(on_complete=lambda *_args: self.active and self._sweep_open())
        anim.start(self)
