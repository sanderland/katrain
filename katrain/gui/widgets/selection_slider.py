from kivy.lang import Builder
from kivy.properties import BooleanProperty, ListProperty, NumericProperty
from kivy.uix.widget import Widget

from katrain.gui.widgets.base import BackgroundLabel  # noqa: F401 -- used from the kv below


class SelectionSlider(Widget):
    __events__ = ["on_select", "on_change"]
    active = BooleanProperty(False)
    hint = BooleanProperty(True)

    index = NumericProperty(0)  # selected index
    values = ListProperty([(0, "")])  # (value:numeric,label:string) pairs
    normalized_pos = NumericProperty(0)  # slider relative pos from 0-1
    px_pos = NumericProperty(0)  # actual px pos
    padding = NumericProperty("16sp")

    track_color = ListProperty([1, 1, 1, 0.3])
    thumb_color = ListProperty([0.5, 0.5, 0.5, 1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(
            size=self.set_index_and_positions,
            pos=self.set_index_and_positions,
            values=self.set_index_and_positions,
            index=self.set_index_and_positions,
        )

    def set_index_and_positions(self, *_args):
        self.index = max(0, min(self.index, len(self.values) - 1))
        self.normalized_pos = self.index / (len(self.values) - 1)
        self.px_pos = self.x + self.padding + self.normalized_pos * (self.width - 2 * self.padding)

    @property
    def value(self):
        return self.values[self.index][0]

    def set_value(self, set_value):  # set to closest value
        if isinstance(set_value, (float, int)):
            eq_value = sorted([(abs(v - set_value), i) for i, (v, _label) in enumerate(self.values)])
            self.index = eq_value[0][1]

    def set_from_pos(self, pos):
        norm_value = (pos[0] - self.x - self.padding) / (self.width - 2 * self.padding)
        self.index = round(norm_value * (len(self.values) - 1))
        self.dispatch("on_change", self.value)

    def on_touch_down(self, touch):
        if self.disabled or not self.collide_point(*touch.pos):
            return
        if touch.is_mouse_scrolling:
            if "down" in touch.button or "left" in touch.button:
                self.index += 1
            if "up" in touch.button or "right" in touch.button:
                self.index -= 1
        else:
            touch.grab(self)
            self.active = True
            self.set_from_pos(touch.pos)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current == self:
            self.set_from_pos(touch.pos)
            return True

    def on_touch_up(self, touch):
        if touch.grab_current == self:
            self.set_from_pos(touch.pos)
            self.active = False
            self.dispatch("on_select", self.value)
            return True

    def on_select(self, value):
        pass

    def on_change(self, value):
        pass


KV = """
#:import i18n katrain.core.lang.i18n

<SelectionSlider>:
    canvas:
        Clear
        Color:
            rgba: self.track_color
        Rectangle:  # track
            size: self.width - self.padding * 2, dp(4)
            pos: self.x + self.padding, self.center_y - dp(4)
        Color:
            rgba: self.thumb_color
        Rectangle:  # filled part of the track
            size: (self.width - self.padding * 2) * self.normalized_pos, dp(4)
            pos: self.x + self.padding, self.center_y - dp(4)
        Ellipse:  # thumb, which grows while being dragged
            size: [dp(24) if self.active else dp(16)] * 2
            pos:
                (self.px_pos - (dp(12) if self.active else dp(8)),
                self.center_y - dp(2) - (dp(12) if self.active else dp(8)))

    BackgroundLabel:  # value hint above the thumb, only shown while dragging
        id: hint_box
        size_hint: None, None
        size: max(dp(28), self.texture_size[0] + 4), dp(28)
        pos: root.px_pos - dp(9), root.center_y - self.height / 2 + dp(30)
        background_color: [1, 1, 1, 1] if root.active else [0, 0, 0, 0]
        background_radius: dp(3)
        text: root.values[root.index][1]
        font_size: sp(12)
        lang_change_tracking: i18n._('')  # for font
        halign: "center"
        color: root.thumb_color if root.active else [0, 0, 0, 0]
"""

Builder.load_string(KV)
