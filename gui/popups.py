from kivy.uix.boxlayout import BoxLayout
import os

from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from game import Game, GameNode
from gui.kivyutils import LabelledFloatInput, LabelledIntInput, LabelledTextInput, StyledButton, LabelledCheckBox


class InputParseError(Exception):
    pass


class QuickConfigGui(BoxLayout):
    def __init__(self, katrain, popup, initial_values=None):
        super().__init__()
        self.katrain = katrain
        self.popup = popup
        if initial_values:
            self.set_properties(self, initial_values)

    def collect_properties(self, widget):
        if isinstance(widget, LabelledTextInput):
            try:
                ret = {widget.input_property: widget.input_value}
            except Exception as e:
                raise InputParseError(f"Could not parse value for {widget.input_property} ({widget.__class__}): {e}")
        else:
            ret = {}
        for c in widget.children:
            for k, v in self.collect_properties(c).items():
                ret[k] = v
        return ret

    def set_properties(self, widget, properties):
        if isinstance(widget, LabelledTextInput):
            key = widget.input_property
            if key in properties:
                widget.text = str(properties[key])
        for c in widget.children:
            self.set_properties(c, properties)


class LoadSGFPopup(BoxLayout):
    pass


class NewGamePopup(QuickConfigGui):
    def new_game(self):
        new_root = GameNode(properties={**Game.DEFAULT_PROPERTIES, **self.collect_properties(self)})
        self.katrain("new-game", None, new_root)
        self.popup.dismiss()


class ConfigPopup(QuickConfigGui):
    @staticmethod
    def type_to_widget_class(value):
        if isinstance(value, float):
            return LabelledFloatInput
        elif isinstance(value, bool):
            return LabelledCheckBox
        elif isinstance(value, int):
            return LabelledIntInput
        else:
            return LabelledTextInput

    def __init__(self, katrain, popup, config):
        self.config = config
        self.orientation = "vertical"
        super().__init__(katrain, popup)
        cols = [BoxLayout(orientation="vertical"), BoxLayout(orientation="vertical")]
        props_in_col = [0, 0]
        for k1, all_d in config.items():
            d = {k: v for k, v in all_d.items() if isinstance(v, (int, float, str, bool))}  # no complex objects
            cat = GridLayout(cols=2, rows=len(d) + 1, size_hint=(1, len(d) + 1))
            cat.add_widget(Label(text="Settings for", bold=True))
            cat.add_widget(Label(text=k1, bold=True))
            for k2, v in d.items():
                cat.add_widget(Label(text=f"{k2}:"))
                print(v, v.__class__, self.type_to_widget_class(v))
                cat.add_widget(self.type_to_widget_class(v)(text=str(v), input_property=f"{k1}/{k2}"))
            if props_in_col[0] <= props_in_col[1]:
                cols[0].add_widget(cat)
                props_in_col[0] += len(d)
            else:
                cols[1].add_widget(cat)
                props_in_col[1] += len(d)

        col_container = BoxLayout(size_hint=(1, 0.95))
        col_container.add_widget(cols[0])
        col_container.add_widget(cols[1])
        self.add_widget(col_container)
        self.save_button = StyledButton(text="Update Settings", on_press=lambda _: self.update_config(), size_hint=(1, 0.05))
        self.add_widget(self.save_button)

    def update_config(self):
        try:
            print(self.collect_properties(self))
            self.popup.dismiss()
        except InputParseError as e:
            self.save_button.text = str(e)
            print(e)
