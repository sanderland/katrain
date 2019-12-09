from kivy.core.text import Label as CoreLabel
from kivy.graphics import *
from kivy.uix.boxlayout import BoxLayout


class CheckBoxHint(BoxLayout):
    __events__ = ("on_active",)

    @property
    def active(self):
        return self.checkbox.active

    def on_active(self, *args):
        pass


class BWCheckBoxHint(BoxLayout):
    __events__ = ("on_active",)

    def active(self, player):
        return [self.black, self.white][player].active

    def on_active(self, *args):
        pass


class CensorableLabel(BoxLayout):
    @property
    def text(self):
        return self.value.text


def draw_text(pos, text, **kw):
    label = CoreLabel(text=text, bold=True, **kw)
    label.refresh()
    Rectangle(texture=label.texture, pos=(pos[0] - label.texture.size[0] / 2, pos[1] - label.texture.size[1] / 2), size=label.texture.size)


def draw_circle(pos, r, col):
    Color(*col)
    Ellipse(pos=(pos[0] - r, pos[1] - r), size=(2 * r, 2 * r))
