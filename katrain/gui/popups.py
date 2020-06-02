import os
import re
from typing import Any, Dict, List, Tuple, Union

from kivy.clock import Clock
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.textfield import MDTextField

from katrain.core.constants import (
    AI_CONFIG_DEFAULT,
    AI_DEFAULT,
    AI_STRATEGIES_RECOMMENDED_ORDER,
    OUTPUT_DEBUG,
    OUTPUT_ERROR,
    OUTPUT_INFO,
)
from katrain.core.engine import KataGoEngine
from katrain.core.lang import i18n
from katrain.core.utils import find_package_resource
from katrain.gui.kivyutils import BackgroundMixin, I18NSpinner
from katrain.gui.style import DEFAULT_FONT, EVAL_COLORS


class I18NPopup(Popup):
    title_key = StringProperty("")
    font_name = StringProperty(DEFAULT_FONT)


class LabelledTextInput(MDTextField):
    input_property = StringProperty("")
    multiline = BooleanProperty(False)

    @property
    def input_value(self):
        return self.text


class LabelledPathInput(LabelledTextInput):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self.check_error, 0)

    def check_error(self, _dt=None):
        file = find_package_resource(self.input_value, silent_errors=True)
        self.error = not (file and os.path.exists(file))

    def on_text(self, widget, text):
        self.check_error()
        return super().on_text(widget, text)

    @property
    def input_value(self):
        return self.text.strip().replace("\n", " ").replace("\r", " ")


class LabelledCheckBox(MDCheckbox):
    input_property = StringProperty("")

    def __init__(self, text=None, **kwargs):
        if text is not None:
            kwargs["active"] = text.lower() == "true"
        super().__init__(**kwargs)

    @property
    def input_value(self):
        return bool(self.active)


class LabelledSpinner(I18NSpinner):
    input_property = StringProperty("")

    @property
    def input_value(self):
        return self.selected[1]  # ref value


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


class InputParseError(Exception):
    pass


class QuickConfigGui(MDBoxLayout):
    def __init__(self, katrain):
        super().__init__()
        self.katrain = katrain
        self.popup = None
        Clock.schedule_once(lambda _dt: self.set_properties(self))

    def collect_properties(self, widget) -> Dict:
        if isinstance(widget, (LabelledTextInput, LabelledSpinner, LabelledCheckBox)) and getattr(
            widget, "input_property", None
        ):
            try:
                ret = {widget.input_property: widget.input_value}
            except Exception as e:
                raise InputParseError(
                    f"Could not parse value for {widget.input_property} ({widget.__class__}): {e}"
                )  # TODO : on widget!
        else:
            ret = {}
        for c in widget.children:
            for k, v in self.collect_properties(c).items():
                ret[k] = v
        return ret

    def get_setting(self, key) -> Union[Tuple[Any, Dict, str], Tuple[Any, List, int]]:
        keys = key.split("/")
        config = self.katrain._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        if "::" in keys[-1]:
            array_key, ix = keys[-1].split("::")
            ix = int(ix)
            array = config[array_key]
            return array[ix], array, ix
        else:
            if keys[-1] not in config:
                config[keys[-1]] = ""
                self.katrain.log(
                    f"Configuration setting {repr(key)} was missing, created it, but this likely indicates a broken config file.",
                    OUTPUT_ERROR,
                )
            return config[keys[-1]], config, keys[-1]

    def set_properties(self, widget):
        if isinstance(widget, (LabelledTextInput, LabelledSpinner, LabelledCheckBox)) and getattr(
            widget, "input_property", None
        ):
            value = self.get_setting(widget.input_property)[0]
            if isinstance(widget, LabelledCheckBox):
                widget.active = value is True
            elif isinstance(widget, LabelledSpinner):
                selected = 0
                try:
                    selected = widget.value_refs.index(value)
                except:
                    pass
                widget.text = widget.values[selected]
            else:
                widget.text = str(value)
        for c in widget.children:
            self.set_properties(c)

    def update_config(self, save_to_file=True):
        updated = set()
        for multikey, value in self.collect_properties(self).items():
            old_value, conf, key = self.get_setting(multikey)
            if value != old_value:
                self.katrain.log(f"Updating setting {multikey} = {value}", OUTPUT_DEBUG)
                conf[key] = value  # reference straight back to katrain._config - may be array or dict
                updated.add(multikey)
        if save_to_file:
            self.katrain.save_config()
        if updated:
            self.katrain.update_state()
        if self.popup:
            self.popup.dismiss()
        return updated


class ConfigTimerPopup(QuickConfigGui):
    def update_config(self, save_to_file=True):
        super().update_config(save_to_file=save_to_file)
        for p in self.katrain.players_info.values():
            p.periods_used = 0
        self.katrain.controls.timer.paused = True
        self.katrain.game.current_node.time_used = 0
        self.katrain.update_state()


class NewGamePopup(QuickConfigGui):
    def __init__(self, katrain):
        super().__init__(katrain)
        self.rules_spinner.value_refs = [name for abbr, name in katrain.engine.RULESETS_ABBR]

    def update_config(self, save_to_file=True):
        super().update_config(save_to_file=save_to_file)
        self.katrain.log(f"New game settings: {self.katrain.config('game')}", OUTPUT_DEBUG)
        if self.restart.active:
            self.katrain.log("Restarting Engine", OUTPUT_DEBUG)
            self.katrain.engine.restart()
        for bw, player_setup in self.player_setup.players.items():
            self.katrain.update_player(bw, **player_setup.player_type_dump)
        self.katrain("new-game")


def wrap_anchor(widget):
    anchor = AnchorLayout()
    anchor.add_widget(widget)
    return anchor


class ConfigTeacherPopup(QuickConfigGui):
    def __init__(self, katrain):
        super().__init__(katrain)
        self.build()

    def add_option_widgets(self, widgets):
        for widget in widgets:
            self.options_grid.add_widget(wrap_anchor(widget))

    def build(self):
        undos = self.katrain.config("trainer/num_undo_prompts")
        thresholds = self.katrain.config("trainer/eval_thresholds")
        savesgfs = self.katrain.config("trainer/save_feedback")
        show_dots = self.katrain.config("trainer/show_dots")

        for i, (color, threshold, undo, show_dot, savesgf) in enumerate(
            zip(EVAL_COLORS, thresholds, undos, show_dots, savesgfs)
        ):
            self.add_option_widgets(
                [
                    BackgroundMixin(background_color=color, size_hint=[0.9, 0.9]),
                    LabelledFloatInput(text=str(threshold), input_property=f"trainer/eval_thresholds::{i}"),
                    LabelledFloatInput(text=str(undo), input_property=f"trainer/num_undo_prompts::{i}"),
                    LabelledCheckBox(text=str(show_dot), input_property=f"trainer/show_dots::{i}"),
                    LabelledCheckBox(text=str(savesgf), input_property=f"trainer/save_feedback::{i}"),
                ]
            )
        self.set_properties(self)


class DescriptionLabel(Label):
    pass


class AIPopup(QuickConfigGui):
    max_options = NumericProperty(6)

    def __init__(self, katrain):
        super().__init__(katrain)
        self.ai_select.value_refs = AI_STRATEGIES_RECOMMENDED_ORDER
        selected_strategies = {p.strategy for p in katrain.players_info.values()}
        config_strategy = list((selected_strategies - {AI_DEFAULT}) or {AI_CONFIG_DEFAULT})[0]
        self.ai_select.select_key(config_strategy)
        self.build_ai_options()
        self.ai_select.bind(text=self.build_ai_options)

    def build_ai_options(self, *_args):
        strategy = self.ai_select.selected[1]
        mode_settings = self.katrain.config(f"ai/{strategy}")
        self.options_grid.clear_widgets()
        self.help_label.text = i18n._(strategy.replace("ai:", "aihelp:"))
        for k, v in sorted(mode_settings.items(), key=lambda kv: kv[0]):
            self.options_grid.add_widget(DescriptionLabel(text=k))
            self.options_grid.add_widget(
                wrap_anchor(LabelledFloatInput(text=str(v), input_property=f"ai/{strategy}/{k}"))
            )
        for _ in range((self.max_options - len(mode_settings)) * 2):
            self.options_grid.add_widget(Label())


class ConfigPopup(QuickConfigGui):
    def __init__(self, katrain):
        super().__init__(katrain)
        self.configfile.text = i18n._("config file path").format(file=katrain.config_file)

    def update_config(self, save_to_file=True):
        updated = super().update_config(save_to_file=save_to_file)
        self.katrain.debug_level = self.katrain.config("general/debug_level", OUTPUT_INFO)

        ignore = {"max_visits", "max_time", "enable_ownership", "wide_root_noise"}
        detected_restart = [key for key in updated if "engine" in key and not any(ig in key for ig in ignore)]
        if detected_restart:

            def restart_engine(_dt):
                self.katrain.log(f"Restarting Engine after {detected_restart} settings change")
                self.katrain.controls.set_status(i18n._("restarting engine"))

                old_engine = self.katrain.engine  # type: KataGoEngine
                old_proc = old_engine.katago_process
                if old_proc:
                    old_engine.shutdown(finish=False)
                new_engine = KataGoEngine(self.katrain, self.katrain.config("engine"))
                self.katrain.engine = new_engine
                self.katrain.game.engines = {"B": new_engine, "W": new_engine}
                self.katrain.game.analyze_all_nodes()  # old engine was possibly broken, so make sure we redo any failures
                self.katrain.update_state()

            Clock.schedule_once(restart_engine, 0)


class LoadSGFPopup(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app = MDApp.get_running_app()
        self.filesel.favorites = [
            (os.path.abspath(app.gui.config("general/sgf_load")), "SGF Load Dir"),
            (os.path.abspath(app.gui.config("general/sgf_save")), "SGF Save Dir"),
        ]
        self.filesel.path = os.path.abspath(os.path.expanduser(app.gui.config("general/sgf_load")))
        self.filesel.select_string = i18n._("Load File")
