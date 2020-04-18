from kivy.uix.boxlayout import BoxLayout
import os
from constants import OUTPUT_DEBUG, OUTPUT_ERROR
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from engine import KataGoEngine
from game import Game, GameNode
from gui.kivyutils import LabelledFloatInput, LabelledIntInput, LabelledTextInput, StyledButton, LabelledCheckBox, LabelledSpinner


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
        if isinstance(widget, (LabelledTextInput, LabelledSpinner)):
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
        if isinstance(widget, (LabelledTextInput, LabelledSpinner)):
            key = widget.input_property
            if key in properties:
                widget.text = str(properties[key])
        for c in widget.children:
            self.set_properties(c, properties)


class LoadSGFPopup(BoxLayout):
    pass


class NewGamePopup(QuickConfigGui):
    def __init__(self, katrain, popup, properties, **kwargs):
        properties["RU"] = KataGoEngine.get_rules(katrain.game.root)
        super().__init__(katrain, popup, properties)
        self.rules_spinner.values = list(set(self.katrain.engine.RULESETS.values()))
        self.rules_spinner.text = properties["RU"]

    def new_game(self):
        properties = self.collect_properties(self)
        self.katrain.log(f"New game settings: {properties}", OUTPUT_DEBUG)
        new_root = GameNode(properties={**Game.DEFAULT_PROPERTIES, **properties})
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
        self.save_button = StyledButton(text="Apply Settings", on_press=lambda _: self.update_config(), size_hint=(1, 0.05))  # apply & save?
        self.add_widget(self.save_button)

    def update_config(self, save_to_file=False):
        updated_cat = []
        try:
            for k, v in self.collect_properties(self).items():
                k1, k2 = k.split("/")
                if self.config[k1][k2] != v:
                    self.katrain.log(f"Updating setting {k} = {v}", OUTPUT_DEBUG)
                    updated_cat.append(k1)
                    self.config[k1][k2] = v
                    # if save_to_file: # TODO
                    #    self.katrain._config_store.put()
            self.popup.dismiss()
        except InputParseError as e:
            self.save_button.text = str(e)  # TODO: nicer error
            self.katrain.log(e, OUTPUT_ERROR)
            return

        if "engine" in updated_cat:
            self.katrain.log("Restarting Engine after settings change")
            old_engine = self.katrain.engine
            self.katrain.engine = KataGoEngine(self.katrain, self.config["engine"])
            self.katrain.game.engine = self.katrain.engine
            old_engine.shutdown(finish=True)
        self.katrain.update_state(redraw_board=True)
