from collections import defaultdict

from kivy.clock import Clock
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
        x, y = new_root.board_size
        if x > 52 or y > 52:
            self.info.text = "Board size too big, should be at most 52"
            return
        self.katrain("new-game", new_root)
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

    def __init__(self, katrain, popup, config, ignore_cats):
        self.config = config
        self.ignore_cats = ignore_cats
        self.orientation = "vertical"
        super().__init__(katrain, popup)
        Clock.schedule_once(self._build, 0)

    def _build(self, _):
        cols = [BoxLayout(orientation="vertical"), BoxLayout(orientation="vertical")]
        props_in_col = [0, 0]
        for k1, all_d in self.config.items():
            if k1 in self.ignore_cats:
                continue
            d = {k: v for k, v in all_d.items() if isinstance(v, (int, float, str, bool))}  # no complex objects
            cat = GridLayout(cols=2, rows=len(d) + 1, size_hint=(1, len(d) + 1))
            cat.add_widget(Label(text=""))
            cat.add_widget(Label(text=f"{k1} settings", bold=True))
            for k2, v in d.items():
                cat.add_widget(Label(text=f"{k2}:"))
                cat.add_widget(self.type_to_widget_class(v)(text=str(v), input_property=f"{k1}/{k2}"))
            if props_in_col[0] <= props_in_col[1]:
                cols[0].add_widget(cat)
                props_in_col[0] += len(d)
            else:
                cols[1].add_widget(cat)
                props_in_col[1] += len(d)

        col_container = BoxLayout(size_hint=(1, 0.9))
        col_container.add_widget(cols[0])
        col_container.add_widget(cols[1])
        self.add_widget(col_container)
        self.info_label = Label()
        self.apply_button = StyledButton(text="Apply", on_press=lambda _: self.update_config())
        self.save_button = StyledButton(text="Apply and Save", on_press=lambda _: self.update_config(save_to_file=True))
        btn_container = BoxLayout(orientation="horizontal", size_hint=(1, 0.1))
        btn_container.add_widget(self.info_label)
        btn_container.add_widget(self.apply_button)
        btn_container.add_widget(self.save_button)
        self.add_widget(btn_container)

    def update_config(self, save_to_file=False):
        updated_cat = defaultdict(list)
        try:
            for k, v in self.collect_properties(self).items():
                k1, k2 = k.split("/")
                if self.config[k1][k2] != v:
                    self.katrain.log(f"Updating setting {k} = {v}", OUTPUT_DEBUG)
                    updated_cat[k1].append(k2)
                    self.config[k1][k2] = v
            self.popup.dismiss()
        except InputParseError as e:
            self.info_label.text = str(e)
            self.katrain.log(e, OUTPUT_ERROR)
            return

        if save_to_file:
            for cat in updated_cat:
                self.katrain.save_config(cat, **self.config[cat])

        engine_restart = False
        for cat, updates in updated_cat.items():
            if "engine" in cat:  # TODO: multi engine support
                if "visits" in updates:
                    self.katrain.engine.visits = self.config[cat]["visits"]
                if set(updates) != {"visits"}:
                    self.katrain.log(f"Restarting Engine {cat} after {updates} settings change")
                    old_engine = self.katrain.engine
                    self.katrain.engine = KataGoEngine(self.katrain, self.config[cat])
                    self.katrain.game.engine = self.katrain.engine
                    old_engine.shutdown(finish=True)
                    engine_restart = True

        if engine_restart:
            self.katrain.update_state(redraw_board=True)
