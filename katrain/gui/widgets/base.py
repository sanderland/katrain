"""Mixins shared by the rest of the KaTrain widgets."""

from kivy.properties import ListProperty, NumericProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget


class BackgroundMixin(Widget):
    """Gives a widget a filled, optionally rounded and outlined, background.

    The drawing itself lives in the ``<BackgroundMixin>`` rule in `gui.kv`.
    """

    background_color = ListProperty([0, 0, 0, 0])
    background_radius = NumericProperty(0)
    outline_color = ListProperty([0, 0, 0, 0])
    outline_width = NumericProperty(1)


class BackgroundLabel(BackgroundMixin, Label):
    pass


class BGBoxLayout(BoxLayout, BackgroundMixin):
    pass


class LeftButtonBehavior(ButtonBehavior):
    """Adds `on_left_press`/`on_left_release`, so right clicks do not activate a button."""

    def __init__(self, **kwargs):
        self.register_event_type("on_left_release")
        self.register_event_type("on_left_press")
        super().__init__(**kwargs)

    def _touched_with_left_button(self):
        return not self.last_touch or "button" not in self.last_touch.profile or self.last_touch.button == "left"

    def on_release(self):
        if self._touched_with_left_button():
            self.dispatch("on_left_release")
        return super().on_release()

    def on_press(self):
        if self._touched_with_left_button():
            self.dispatch("on_left_press")
        return super().on_press()

    def on_left_release(self):
        pass

    def on_left_press(self):
        pass
