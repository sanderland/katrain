"""Material Design touch ripple, drawn on top of the host widget.

Mix :class:`RectangularRippleBehavior` or :class:`CircularRippleBehavior` into a
widget that also has a :class:`~kivy.uix.behaviors.ButtonBehavior`, listing the
ripple *before* the button behaviour so that the ripple sees the touch first::

    class MyButton(RectangularRippleBehavior, ButtonBehavior, Widget):
        pass
"""

from kivy.animation import Animation
from kivy.graphics import Canvas, Color, Ellipse, Rectangle, StencilPop, StencilPush, StencilUnUse, StencilUse
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty

from katrain.gui.theme import Theme


class RippleBehavior:
    """Expanding-and-fading circle that follows a touch, clipped to the widget.

    The ripple gets its own layer inside the host's ``canvas.after`` rather than
    drawing there directly, so that clearing it up cannot take anything else drawn
    on the widget with it (`BadukPanWidget` draws the pass-move policy hint onto the
    pass button that way), nor be taken out by such a redraw mid-ripple.
    """

    _ripple_layer = None

    ripple_color = ListProperty(Theme.RIPPLE_COLOR)
    ripple_alpha = NumericProperty(0.5)
    ripple_scale = NumericProperty(1)  # final radius as a multiple of the widget size
    ripple_start_radius = NumericProperty(1)

    ripple_duration_in_fast = NumericProperty(0.3)  # expansion after the touch is released
    ripple_duration_in_slow = NumericProperty(2)  # expansion while the touch is held
    ripple_duration_out = NumericProperty(0.3)
    ripple_func_in = StringProperty("out_quad")
    ripple_func_out = StringProperty("out_quad")

    _ripple_radius = NumericProperty(0)
    _expanding = BooleanProperty(False)
    _releasing = BooleanProperty(False)
    _fading_out = BooleanProperty(False)

    def on_touch_down(self, touch):
        if touch.is_mouse_scrolling or not self.collide_point(touch.x, touch.y):
            return False
        if not self.disabled:
            self._start_ripple(touch.pos)
        return super().on_touch_down(touch)

    def on_touch_move(self, touch, *args):
        if self._expanding and not self._releasing and not self.collide_point(touch.x, touch.y):
            self._release_ripple()
        return super().on_touch_move(touch, *args)

    def on_touch_up(self, touch):
        if self._expanding and not self._releasing and self.collide_point(touch.x, touch.y):
            self._release_ripple()
        return super().on_touch_up(touch)

    def anim_complete(self, *_args):
        """Cancel any running ripple and take its layer back off the canvas."""
        Animation.cancel_all(self, "_ripple_radius", "ripple_color")
        self.unbind(ripple_color=self._set_ripple_color, _ripple_radius=self._set_ripple_radius)
        self._expanding = self._releasing = self._fading_out = False
        if self._ripple_layer is not None:
            if self._ripple_layer in self.canvas.after.children:  # a redraw may have cleared it already
                self.canvas.after.remove(self._ripple_layer)
            self._ripple_layer = None

    # -- internals

    def _start_ripple(self, pos):
        if self._expanding:
            self.anim_complete()
        self.ripple_pos = pos
        self._ripple_radius = self.ripple_start_radius
        self.ripple_color = [*self.ripple_color[:3], self.ripple_alpha]
        self._final_radius = max(self.width, self.height) * self.ripple_scale
        self._ripple_layer = Canvas()
        self.canvas.after.add(self._ripple_layer)
        self._draw_ripple()
        self._expanding = True
        anim = Animation(_ripple_radius=self._final_radius, t="linear", duration=self.ripple_duration_in_slow)
        anim.bind(on_complete=self._fade_out)
        anim.start(self)

    def _release_ripple(self):
        """Speed the expansion up now that the touch is over, then fade out."""
        Animation.cancel_all(self, "_ripple_radius")
        self._releasing = True
        anim = Animation(
            _ripple_radius=self._final_radius, t=self.ripple_func_in, duration=self.ripple_duration_in_fast
        )
        anim.bind(on_complete=self._fade_out)
        anim.start(self)

    def _fade_out(self, *_args):
        if self._fading_out:
            return
        self._fading_out = True
        Animation.cancel_all(self, "ripple_color")
        anim = Animation(
            ripple_color=[*self.ripple_color[:3], 0.0], t=self.ripple_func_out, duration=self.ripple_duration_out
        )
        anim.bind(on_complete=self.anim_complete)
        anim.start(self)

    def _draw_ripple(self):
        """Fill :attr:`_ripple_layer` with the ripple, clipped to the widget's shape."""
        raise NotImplementedError

    def _set_ripple_color(self, _instance, value):
        self._ripple_color_instruction.a = value[3]

    def _set_ripple_radius(self, _instance, _value):
        raise NotImplementedError


class RectangularRippleBehavior(RippleBehavior):
    """Ripple clipped to the widget's bounding box, centered on the touch."""

    ripple_scale = NumericProperty(2.75)

    def _draw_ripple(self):
        with self._ripple_layer:
            StencilPush()
            Rectangle(pos=self.pos, size=self.size)
            StencilUse()
            self._ripple_color_instruction = Color(rgba=self.ripple_color)
            self._ripple_ellipse = Ellipse(size=(0, 0))
            StencilUnUse()
            Rectangle(pos=self.pos, size=self.size)
            StencilPop()
        self._set_ripple_radius(self, self._ripple_radius)
        self.bind(ripple_color=self._set_ripple_color, _ripple_radius=self._set_ripple_radius)

    def _set_ripple_radius(self, _instance, _value):
        radius = self._ripple_radius
        self._ripple_ellipse.size = (radius, radius)
        self._ripple_ellipse.pos = (self.ripple_pos[0] - radius / 2, self.ripple_pos[1] - radius / 2)


class CircularRippleBehavior(RippleBehavior):
    """Ripple clipped to a circle around the widget's center."""

    ripple_scale = NumericProperty(1)

    def _draw_ripple(self):
        with self._ripple_layer:
            StencilPush()
            Ellipse(
                size=(self.width * self.ripple_scale, self.height * self.ripple_scale),
                pos=(
                    self.center_x - self.width * self.ripple_scale / 2,
                    self.center_y - self.height * self.ripple_scale / 2,
                ),
            )
            StencilUse()
            self._ripple_color_instruction = Color(rgba=self.ripple_color)
            self._ripple_ellipse = Ellipse(size=(0, 0))
            StencilUnUse()
            Ellipse(pos=self.pos, size=self.size)
            StencilPop()
        self._set_ripple_radius(self, self._ripple_radius)
        self.bind(ripple_color=self._set_ripple_color, _ripple_radius=self._set_ripple_radius)

    def _set_ripple_radius(self, _instance, _value):
        radius = self._ripple_radius
        self._ripple_ellipse.size = (radius, radius)
        self._ripple_ellipse.pos = (self.center_x - radius / 2, self.center_y - radius / 2)
        if radius > self.width * 0.6:
            self._fade_out()
