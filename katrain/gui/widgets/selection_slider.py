from kivy.lang import Builder
from kivy.properties import BooleanProperty, ListProperty, NumericProperty
from kivy.uix.widget import Widget


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
        eq_value = sorted([(abs(v - set_value), i) for i, (v, l) in enumerate(self.values)])
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
    id: slider
    canvas:
        Clear
        Color:
            rgba:
                self.track_color
        Rectangle:
            size:
                (self.width - self.padding*2, dp(4))
            pos:
                (self.x + self.padding, self.center_y - dp(4))
        Color:
            rgba:
                self.thumb_color
        Rectangle:
            size:
                ((self.width-self.padding*2)*self.normalized_pos, sp(4))
            pos:
                (self.x + self.padding, self.center_y - dp(4))

    Thumb:
        id: thumb
        size_hint: None, None
        size:
            ((dp(24), dp(24))   if root.active else (dp(16), dp(16)))
        pos:
            (slider.px_pos - dp(8), slider.center_y - thumb.height/2 - dp(2))
        color:
            root.thumb_color
        elevation:
            4 if root.active else 2

    MDCard:
        id: hint_box
        size_hint: None, None
        md_bg_color: [1, 1, 1, 1] if root.active else [0, 0, 0, 0]
        elevation: 4 if root.active else 0
        size:
            (max(dp(28), label.texture_size[0]+4) , dp(28))
        pos:
            (slider.px_pos - dp(9), slider.center_y - hint_box.height / 2 + dp(30))

        Label:
            id: label
            text: slider.values[slider.index][1]
            font_size: sp(12)
            lang_change_tracking: i18n._('') # for font
            halign: "center"
            color: root.thumb_color if root.active else [0, 0, 0, 0]
"""

Builder.load_string(KV)
