from kivy.core.text import Label as CoreLabel
from kivy.graphics import *
from kivy.properties import BooleanProperty, StringProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
import re

from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput


class StyledButton(Button):
    pass


class CheckBoxHint(BoxLayout):
    __events__ = ("on_active",)

    @property
    def active(self):
        return self.checkbox.active

    def on_active(self, *args):
        pass

class DarkLabel(Label):
    pass

class BaseCircleWithText(DarkLabel):
    radius = NumericProperty(0.48)

class LabelledTextInput(TextInput):
    input_property = StringProperty("")

    @property
    def input_value(self):
        return self.text


class LabelledCheckBox(CheckBox):
    input_property = StringProperty("")

    def __init__(self, text=None, **kwargs):
        if text is not None:
            kwargs["active"] = bool(text)
        super().__init__(**kwargs)

    @property
    def input_value(self):
        return bool(self.active)


class LabelledSpinner(Spinner):
    input_property = StringProperty("")

    @property
    def input_value(self):
        return self.text


class LabelledFloatInput(LabelledTextInput):
    signed = BooleanProperty(True)
    pat = re.compile("[^0-9-]")

    def insert_text(self, substring, from_undo=False):
        pat = self.pat
        if "." in self.text:
            s = re.sub(pat, "", substring)
        else:
            s = ".".join([re.sub(pat, "", s) for s in substring.split(".", 1)])
        r = super().insert_text(s, from_undo=from_undo)
        if not self.signed and "-" in self.text:
            self.text = self.text.replace("-", "")
        elif self.text and "-" in self.text[1:]:
            self.text = self.text[0] + self.text[1:].replace("-", "")
        return r

    @property
    def input_value(self):
        return float(self.text)


class LabelledIntInput(LabelledTextInput):
    pat = re.compile("[^0-9]")

    def insert_text(self, substring, from_undo=False):
        return super().insert_text(re.sub(self.pat, "", substring), from_undo=from_undo)

    @property
    def input_value(self):
        return int(self.text)


class BWCheckBoxHint(BoxLayout):
    __events__ = ("on_active",)

    @property
    def active_map(self):
        return {"B": self.black.active, "W": self.white.active}

    def active(self, player):
        return self.active_map[player]

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
