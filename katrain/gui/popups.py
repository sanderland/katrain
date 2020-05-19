from collections import defaultdict
from typing import Dict, List, DefaultDict, Tuple

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from katrain.core.common import OUTPUT_DEBUG, OUTPUT_ERROR
from katrain.core.engine import KataGoEngine
from katrain.core.game import Game, GameNode
from katrain.gui.kivyutils import (
    BackgroundLabel,
    LabelledCheckBox,
    LabelledFloatInput,
    LabelledIntInput,
    LabelledObjectInputArea,
    LabelledSpinner,
    LabelledTextInput,
    LightHelpLabel,
    ScaledLightLabel,
    StyledButton,
    StyledSpinner,
)


class InputParseError(Exception):
    pass


class QuickConfigGui(BoxLayout):
    def __init__(self, katrain, popup: Popup, initial_values: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.katrain = katrain
        self.popup = popup
        self.orientation = "vertical"
        if initial_values:
            self.set_properties(self, initial_values)

    @staticmethod
    def type_to_widget_class(value):
        if isinstance(value, float):
            return LabelledFloatInput
        elif isinstance(value, bool):
            return LabelledCheckBox
        elif isinstance(value, int):
            return LabelledIntInput
        if isinstance(value, dict):
            return LabelledObjectInputArea
        else:
            return LabelledTextInput

    def collect_properties(self, widget):
        if isinstance(widget, (LabelledTextInput, LabelledSpinner, LabelledCheckBox)):
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
    def __init__(self, katrain, popup: Popup, properties: Dict, **kwargs):
        properties["RU"] = KataGoEngine.get_rules(katrain.game.root)
        super().__init__(katrain, popup, properties, **kwargs)
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
        if self.restart.active:
            self.katrain.log("Restarting Engine")
            self.katrain.engine.restart()
        self.katrain("new-game", new_root)
        self.popup.dismiss()


class ConfigPopup(QuickConfigGui):
    def __init__(self, katrain, popup: Popup, config: Dict, ignore_cats: Tuple = (), **kwargs):
        self.config = config
        self.ignore_cats = ignore_cats
        self.orientation = "vertical"
        super().__init__(katrain, popup, **kwargs)
        Clock.schedule_once(self.build, 0)

    def build(self, _):

        props_in_col = [0, 0]
        cols = [BoxLayout(orientation="vertical"), BoxLayout(orientation="vertical")]

        for k1, all_d in sorted(self.config.items(), key=lambda tup: -len(tup[1])):  # sort to make greedy bin packing work better
            if k1 in self.ignore_cats:
                continue
            d = {k: v for k, v in all_d.items() if isinstance(v, (int, float, str, bool)) and not k.startswith("_")}  # no lists . dict could be supported but hard to scale
            cat = GridLayout(cols=2, rows=len(d) + 1, size_hint=(1, len(d) + 1))
            cat.add_widget(Label(text=""))
            cat.add_widget(ScaledLightLabel(text=f"{k1} settings", bold=True))
            for k2, v in d.items():
                label = ScaledLightLabel(text=f"{k2}:")
                widget = self.type_to_widget_class(v)(text=str(v), input_property=f"{k1}/{k2}")
                hint = all_d.get("_hint_" + k2)
                if hint:
                    label.tooltip_text = hint
                    if isinstance(widget, LabelledTextInput):
                        widget.hint_text = hint
                cat.add_widget(label)
                cat.add_widget(widget)
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
        self.info_label = Label(halign="center")
        self.apply_button = StyledButton(text="Apply", on_press=lambda _: self.update_config())
        self.save_button = StyledButton(text="Apply and Save", on_press=lambda _: self.update_config(save_to_file=True))
        btn_container = BoxLayout(orientation="horizontal", size_hint=(1, 0.1), spacing=1, padding=1)
        btn_container.add_widget(self.apply_button)
        btn_container.add_widget(self.info_label)
        btn_container.add_widget(self.save_button)
        self.add_widget(btn_container)

    def update_config(self, save_to_file=False):
        updated_cat = defaultdict(list)  # type: DefaultDict[List[str]]
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
            self.katrain.save_config()

        engine_updates = updated_cat["engine"]
        if "visits" in engine_updates:
            self.katrain.engine.visits = engine_updates["visits"]
        if {key for key in engine_updates if key not in {"max_visits", "max_time", "enable_ownership", "wide_root_noise"}}:
            self.katrain.log(f"Restarting Engine after {engine_updates} settings change")
            self.info_label.text = "Restarting engine\nplease wait."
            self.katrain.controls.set_status(f"Restarted Engine after {engine_updates} settings change.")

            def restart_engine(_dt):
                old_engine = self.katrain.engine  # type: KataGoEngine
                old_proc = old_engine.katago_process
                if old_proc:
                    old_engine.shutdown(finish=True)
                new_engine = KataGoEngine(self.katrain, self.config["engine"])
                self.katrain.engine = new_engine
                self.katrain.game.engines = {"B": new_engine, "W": new_engine}
                self.katrain.game.analyze_all_nodes()  # old engine was possibly broken, so make sure we redo any failures
                self.katrain.update_state()

            Clock.schedule_once(restart_engine, 0)

        self.katrain.debug_level = self.config["debug"]["level"]
        self.katrain.update_state(redraw_board=True)


class ConfigAIPopup(QuickConfigGui):
    def __init__(self, katrain, popup: Popup, settings):
        super().__init__(katrain, popup, settings)
        self.settings = settings
        Clock.schedule_once(self.build, 0)

    def build(self, _):
        ais = list(self.settings.keys())

        top_bl = BoxLayout()
        top_bl.add_widget(ScaledLightLabel(text="Select AI to configure:"))
        ai_spinner = StyledSpinner(values=ais, text=ais[0])
        ai_spinner.fbind("text", lambda _, text: self.build_ai_options(text))
        top_bl.add_widget(ai_spinner)
        self.add_widget(top_bl)
        self.options_grid = GridLayout(cols=2, rows=max(len(v) for v in self.settings.values()) - 1, size_hint=(1, 7.5), spacing=1)  # -1 for help in 1 col
        bottom_bl = BoxLayout(spacing=2)
        self.info_label = Label()
        bottom_bl.add_widget(StyledButton(text=f"Apply", on_press=lambda _: self.update_config(False)))
        bottom_bl.add_widget(self.info_label)
        bottom_bl.add_widget(StyledButton(text=f"Apply and Save", on_press=lambda _: self.update_config(True)))
        self.add_widget(self.options_grid)
        self.add_widget(bottom_bl)
        self.build_ai_options(ais[0])

    def build_ai_options(self, mode):
        mode_settings = self.settings[mode]
        self.options_grid.clear_widgets()
        self.options_grid.add_widget(LightHelpLabel(size_hint=(1, 4), padding=(2, 2), text=mode_settings.get("_help_left", "")))
        self.options_grid.add_widget(LightHelpLabel(size_hint=(1, 4), padding=(2, 2), text=mode_settings.get("_help_right", "")))
        for k, v in mode_settings.items():
            if not k.startswith("_"):
                self.options_grid.add_widget(ScaledLightLabel(text=f"{k}"))
                self.options_grid.add_widget(ConfigPopup.type_to_widget_class(v)(text=str(v), input_property=f"{mode}/{k}"))
        for _ in range(self.options_grid.rows * self.options_grid.cols - len(self.options_grid.children)):
            self.options_grid.add_widget(ScaledLightLabel(text=f""))
        self.set_properties(self, self.settings)

    def update_config(self, save_to_file=False):
        try:
            for k, v in self.collect_properties(self).items():
                k1, k2 = k.split("/")
                if self.settings[k1][k2] != v:
                    self.settings[k1][k2] = v
                    self.katrain.log(f"Updating setting {k} = {v}", OUTPUT_DEBUG)
            if save_to_file:
                self.katrain.save_config()
            self.popup.dismiss()
        except InputParseError as e:
            self.info_label.text = str(e)
            self.katrain.log(e, OUTPUT_ERROR)
            return
        self.popup.dismiss()


class ConfigTeacherPopup(QuickConfigGui):
    def __init__(self, katrain, popup, **kwargs):
        self.settings = katrain.config("trainer")
        self.sgf_settings = katrain.config("sgf")
        self.ui_settings = katrain.config("board_ui")
        super().__init__(katrain, popup, self.settings, **kwargs)
        self.spacing = 2
        Clock.schedule_once(self.build, 0)

    def build(self, _dt):
        thresholds = self.settings["eval_thresholds"]
        undos = self.settings["num_undo_prompts"]
        colors = self.ui_settings["eval_colors"]
        thrbox = GridLayout(spacing=1, padding=2, cols=5, rows=len(thresholds) + 1)
        thrbox.add_widget(ScaledLightLabel(text="Point loss greater than", bold=True))
        thrbox.add_widget(ScaledLightLabel(text="Gives this many undos", bold=True))
        thrbox.add_widget(ScaledLightLabel(text="Color (fixed)", bold=True))
        thrbox.add_widget(ScaledLightLabel(text="Show dots", bold=True))
        thrbox.add_widget(ScaledLightLabel(text="Save in SGF", bold=True))
        for i, (thr, undos, color) in enumerate(zip(thresholds, undos, colors)):
            thrbox.add_widget(LabelledFloatInput(text=str(thr), input_property=f"eval_thresholds::{i}"))
            thrbox.add_widget(LabelledFloatInput(text=str(undos), input_property=f"num_undo_prompts::{i}"))
            thrbox.add_widget(BackgroundLabel(background=color[:3]))
            thrbox.add_widget(LabelledCheckBox(text=str(color[3] == 1), input_property=f"alpha::{i}"))
            thrbox.add_widget(LabelledCheckBox(size_hint=(0.5, 1), text=str(self.sgf_settings["save_feedback"][i]), input_property=f"save_feedback::{i}"))
        self.add_widget(thrbox)

        xsettings = BoxLayout(size_hint=(1, 0.15), spacing=2)
        xsettings.add_widget(ScaledLightLabel(text="Show last <n> dots"))
        xsettings.add_widget(LabelledIntInput(size_hint=(0.5, 1), text=str(self.settings["eval_off_show_last"]), input_property="eval_off_show_last"))
        self.add_widget(xsettings)
        xsettings = BoxLayout(size_hint=(1, 0.15), spacing=2)
        xsettings.add_widget(ScaledLightLabel(text="Show dots/SGF comments for AI players"))
        xsettings.add_widget(LabelledCheckBox(size_hint=(0.5, 1), text=str(self.settings["eval_show_ai"]), input_property="eval_show_ai"))
        self.add_widget(xsettings)
        xsettings = BoxLayout(size_hint=(1, 0.15), spacing=2)
        xsettings.add_widget(ScaledLightLabel(text="Disable analysis while in teach mode"))
        xsettings.add_widget(LabelledCheckBox(size_hint=(0.5, 1), text=str(self.settings["lock_ai"]), input_property="lock_ai"))
        self.add_widget(xsettings)

        bl = BoxLayout(size_hint=(1, 0.15), spacing=2)
        bl.add_widget(StyledButton(text=f"Apply", on_press=lambda _: self.update_config(False)))
        self.info_label = Label()
        bl.add_widget(self.info_label)
        bl.add_widget(StyledButton(text=f"Apply and Save", on_press=lambda _: self.update_config(True)))
        self.add_widget(bl)

    def update_config(self, save_to_file=False):
        try:
            for k, v in self.collect_properties(self).items():
                if "::" in k:
                    k1, i = k.split("::")
                    i = int(i)
                    if "alpha" in k1:
                        v = 1.0 if v else 0.0
                        if self.ui_settings["eval_colors"][i][3] != v:
                            self.katrain.log(f"Updating alpha {i} = {v}", OUTPUT_DEBUG)
                            self.ui_settings["eval_colors"][i][3] = v
                    elif "save_feedback" in k1:
                        if self.sgf_settings[k1][i] != v:
                            self.sgf_settings[k1][i] = v
                            self.katrain.log(f"Updating setting sgf/{k1}[{i}] = {v}", OUTPUT_DEBUG)

                    else:
                        if self.settings[k1][i] != v:
                            self.settings[k1][i] = v
                            self.katrain.log(f"Updating setting trainer/{k1}[{i}] = {v}", OUTPUT_DEBUG)
                else:
                    if self.settings[k] != v:
                        self.settings[k] = v
                        self.katrain.log(f"Updating setting {k} = {v}", OUTPUT_DEBUG)
            if save_to_file:
                self.katrain.save_config()
            self.popup.dismiss()
        except InputParseError as e:
            self.info_label.text = str(e)
            self.katrain.log(e, OUTPUT_ERROR)
            return
        self.katrain.update_state()
        self.popup.dismiss()


class ConfigTimerPopup(QuickConfigGui):
    def __init__(self, katrain, popup, **kwargs):
        self.settings = katrain.config("timer")
        super().__init__(katrain, popup, self.settings, **kwargs)
        self.spacing = 2
        Clock.schedule_once(self.build, 0)

    def build(self, _dt):
        thrbox = GridLayout(spacing=1, padding=2, cols=2, rows=2, size_hint=(1, 2))
        thrbox.add_widget(ScaledLightLabel(text="Byo-yomi\nperiod length (s)", bold=True, size_hint=(2, 1), num_lines=2))
        thrbox.add_widget(LabelledIntInput(text="30", input_property="byo_length"))
        thrbox.add_widget(ScaledLightLabel(text="Byo-yomi\nnumber of periods", bold=True, size_hint=(2, 1), num_lines=2))
        thrbox.add_widget(LabelledIntInput(text="5", input_property="byo_num"))
        self.add_widget(thrbox)
        self.add_widget(StyledButton(text=f"Apply", on_press=lambda _: self.update_config(False)))

    def update_config(self, save_to_file=False):
        for k, v in self.collect_properties(self).items():
            self.settings[k] = v
        if save_to_file:
            self.katrain.save_config()
        self.katrain.controls.periods_used = {"B": 0, "W": 0}
        self.katrain.update_state()
        self.popup.dismiss()
