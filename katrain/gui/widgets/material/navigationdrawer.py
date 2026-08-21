"""Slide-in navigation drawer with a dimming scrim over the rest of the screen.

Put a :class:`NavigationLayout` at the root of the screen with the regular
content first and the :class:`NavigationDrawer` last; the drawer then slides in
over that content and dims it.
"""

from kivy.animation import Animation, AnimationTransition
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.lang import Builder
from kivy.properties import BooleanProperty, ColorProperty, NumericProperty, OptionProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout

Builder.load_string(
    """
<NavigationDrawer>:
    size_hint_x: None
    x: self.width * (self.open_progress - 1)
"""
)


class NavigationLayout(FloatLayout):
    """Holds the screen content plus a :class:`NavigationDrawer` drawn on top of it."""

    scrim_color = ColorProperty([0, 0, 0, 0.5])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._scrim_color_instruction = None
        self._scrim_rectangle = None

    def add_widget(self, widget, *args, **kwargs):
        if not isinstance(widget, NavigationDrawer) and self._scrim_rectangle is None:
            self._add_scrim(widget)
        return super().add_widget(widget, *args, **kwargs)

    def set_scrim_opacity(self, opacity):
        if self._scrim_color_instruction is not None:
            self._scrim_color_instruction.rgba = [*self.scrim_color[:3], self.scrim_color[3] * opacity]

    def _add_scrim(self, widget):
        """Draw the dimming overlay on top of `widget`, initially fully transparent."""
        with widget.canvas.after:
            self._scrim_color_instruction = Color(rgba=[0, 0, 0, 0])
            self._scrim_rectangle = Rectangle(pos=widget.pos, size=widget.size)
        widget.bind(pos=self._update_scrim_rectangle, size=self._update_scrim_rectangle)

    def _update_scrim_rectangle(self, widget, _value):
        self._scrim_rectangle.pos = widget.pos
        self._scrim_rectangle.size = widget.size


class NavigationDrawer(BoxLayout):
    """Panel that slides in from the side, by dragging its edge or via :meth:`set_state`."""

    state = OptionProperty("close", options=("close", "open"))  # where it is heading, not where it is
    open_progress = NumericProperty(0.0)  # 0 fully closed, 1 fully open

    close_on_click = BooleanProperty(True)  # close on escape or a click outside the drawer
    swipe_edge_width = NumericProperty(20)  # width of the screen edge that starts an opening swipe
    swipe_distance = NumericProperty(10)  # movement needed before a swipe takes hold

    opening_time = NumericProperty(0.2)
    opening_transition = StringProperty("out_cubic")
    closing_time = NumericProperty(0.2)
    closing_transition = StringProperty("out_sine")
    scrim_transition = StringProperty("linear")

    def __init__(self, **kwargs):
        self._swiping = False  # True while the user is dragging the drawer open or shut
        self._open_at_touch_down = False
        super().__init__(**kwargs)
        Window.bind(on_keyboard=self._on_keyboard)

    def set_state(self, new_state="toggle", animation=True):
        if new_state == "toggle":
            new_state = "close" if self.state == "open" else "open"
        opening = new_state == "open"
        target = 1.0 if opening else 0.0
        # Set the state before animating: a toggle part-way through an animation has to see
        # where the drawer is going, or it just re-issues the move it is already making.
        self.state = new_state
        Animation.cancel_all(self, "open_progress")
        if not animation or self.open_progress == target:
            self.open_progress = target
            return
        duration = (
            (self.opening_time * (1 - self.open_progress)) if opening else (self.closing_time * self.open_progress)
        )
        transition = self.opening_transition if opening else self.closing_transition
        Animation(open_progress=target, d=duration, t=transition).start(self)

    def on_open_progress(self, _instance, progress):
        if isinstance(self.parent, NavigationLayout):
            self.parent.set_scrim_opacity(getattr(AnimationTransition, self.scrim_transition)(progress))

    def on_touch_down(self, touch):
        # The click that opens the drawer necessarily lands outside it, and its release must
        # not then count as a click-outside. Only a touch that *started* while we were already
        # open can close us, so remember that here.
        self._open_at_touch_down = self.state == "open"
        if not self._open_at_touch_down:
            return False  # let the swipe detection in on_touch_move deal with it
        for child in self.children[:]:
            if child.dispatch("on_touch_down", touch):
                return True
        return True  # an open drawer swallows touches meant for what is underneath it

    def on_touch_move(self, touch):
        if not self._swiping:
            starts_swipe_open = touch.ox <= self.swipe_edge_width and abs(touch.x - touch.ox) > self.swipe_distance
            if self.state != "open" and not starts_swipe_open:
                return super().on_touch_move(touch)
            self._swiping = True
        self.open_progress = max(0.0, min(1.0, self.open_progress + touch.dx / self.width))
        return True

    def on_touch_up(self, touch):
        if self._swiping:
            self._swiping = False
            self.set_state("open" if self.open_progress > 0.5 else "close")
            return True
        if not self._open_at_touch_down:
            return False
        if self.close_on_click and not self.collide_point(touch.ox, touch.oy):
            self.set_state("close")
        return True

    def _on_keyboard(self, _window, key, *_args):
        if key == 27 and self.state == "open" and self.close_on_click:  # escape
            self.set_state("close")
            return True
