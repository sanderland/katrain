import glob
import json
import os
import re
import stat
import threading
import time
from typing import Any, Dict, List, Tuple, Union
from zipfile import ZipFile

import urllib3
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.textfield import MDTextField

from katrain.core.ai import ai_rank_estimation, game_report
from katrain.core.constants import (
    AI_CONFIG_DEFAULT,
    AI_DEFAULT,
    AI_KEY_PROPERTIES,
    AI_OPTION_VALUES,
    AI_STRATEGIES_RECOMMENDED_ORDER,
    DATA_FOLDER,
    OUTPUT_DEBUG,
    OUTPUT_ERROR,
    OUTPUT_INFO,
    SGF_INTERNAL_COMMENTS_MARKER,
    STATUS_INFO,
    PLAYER_HUMAN,
    ADDITIONAL_MOVE_ORDER,
)
from katrain.core.engine import KataGoEngine
from katrain.core.lang import i18n, rank_label
from katrain.core.sgf_parser import Move
from katrain.core.utils import PATHS, find_package_resource, evaluation_class
from katrain.gui.kivyutils import (
    BackgroundMixin,
    I18NSpinner,
    BackgroundLabel,
    TableHeaderLabel,
    TableCellLabel,
    TableStatLabel,
    PlayerInfo,
    SizedRectangleButton,
    AutoSizedRectangleButton,
)
from katrain.gui.theme import Theme
from katrain.gui.widgets.progress_loader import ProgressLoader


class I18NPopup(Popup):
    title_key = StringProperty("")
    font_name = StringProperty(Theme.DEFAULT_FONT)

    def __init__(self, size=None, **kwargs):
        if size:  # do not exceed window size
            app = MDApp.get_running_app()
            size[0] = min(app.gui.width, size[0])
            size[1] = min(app.gui.height, size[1])
        super().__init__(size=size, **kwargs)
        self.bind(on_dismiss=Clock.schedule_once(lambda _dt: MDApp.get_running_app().gui.update_state(), 1))


class LabelledTextInput(MDTextField):
    input_property = StringProperty("")
    multiline = BooleanProperty(False)

    @property
    def input_value(self):
        return self.text

    @property
    def raw_input_value(self):
        return self.text


class LabelledPathInput(LabelledTextInput):
    check_path = BooleanProperty(True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self.check_error, 0)

    def check_error(self, _dt=None):
        file = find_package_resource(self.input_value, silent_errors=True)
        self.error = self.check_path and not (file and os.path.exists(file))

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

    def raw_input_value(self):
        return self.active


class LabelledSpinner(I18NSpinner):
    input_property = StringProperty("")

    @property
    def input_value(self):
        return self.selected[1]  # ref value

    def raw_input_value(self):
        return self.text


class LabelledFloatInput(LabelledTextInput):
    input_filter = ObjectProperty("float")

    @property
    def input_value(self):
        return float(self.text or "0.0")


class LabelledIntInput(LabelledTextInput):
    input_filter = ObjectProperty("int")

    @property
    def input_value(self):
        return int(self.text or "0")


class LabelledSelectionSlider(BoxLayout):
    input_property = StringProperty("")
    values = ListProperty([(0, "")])  # (value:numeric,label:string) pairs
    key_option = BooleanProperty(False)

    def set_value(self, v):
        self.slider.set_value(v)
        self.textbox.text = str(v)

    @property
    def input_value(self):
        if self.textbox.text:
            return float(self.textbox.text)
        return self.slider.values[self.slider.index][0]

    @property
    def raw_input_value(self):
        return self.textbox.text


class InputParseError(Exception):
    pass


class QuickConfigGui(MDBoxLayout):
    def __init__(self, katrain):
        super().__init__()
        self.katrain = katrain
        self.popup = None
        Clock.schedule_once(self.build_and_set_properties, 0)

    def collect_properties(self, widget) -> Dict:
        if isinstance(
            widget, (LabelledTextInput, LabelledSpinner, LabelledCheckBox, LabelledSelectionSlider)
        ) and getattr(widget, "input_property", None):
            try:
                ret = {widget.input_property: widget.input_value}
            except Exception as e:  # TODO : on widget?
                raise InputParseError(
                    f"Could not parse value '{widget.raw_input_value}' for {widget.input_property} ({widget.__class__.__name__}): {e}"
                )
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

    def build_and_set_properties(self, *_args):
        return self._set_properties_subtree(self)

    def _set_properties_subtree(self, widget):
        if isinstance(
            widget, (LabelledTextInput, LabelledSpinner, LabelledCheckBox, LabelledSelectionSlider)
        ) and getattr(widget, "input_property", None):
            value = self.get_setting(widget.input_property)[0]
            if isinstance(widget, LabelledCheckBox):
                widget.active = value is True
            elif isinstance(widget, LabelledSelectionSlider):
                widget.set_value(value)
            elif isinstance(widget, LabelledSpinner):
                selected = 0
                try:
                    selected = widget.value_refs.index(value)
                except:  # noqa: E722
                    pass
                widget.text = widget.values[selected]
            else:
                widget.text = str(value)
        for c in widget.children:
            self._set_properties_subtree(c)

    def update_config(self, save_to_file=True, close_popup=True):
        updated = set()
        for multikey, value in self.collect_properties(self).items():
            old_value, conf, key = self.get_setting(multikey)
            if value != old_value:
                self.katrain.log(f"Updating setting {multikey} = {value}", OUTPUT_DEBUG)
                conf[key] = value  # reference straight back to katrain._config - may be array or dict
                updated.add(multikey)
        if save_to_file:
            self.katrain.save_config()
        if self.popup and close_popup:
            self.popup.dismiss()
        return updated


class ConfigTimerPopup(QuickConfigGui):
    def update_config(self, save_to_file=True, close_popup=True):
        super().update_config(save_to_file=save_to_file, close_popup=close_popup)
        for p in self.katrain.players_info.values():
            p.periods_used = 0
        self.katrain.controls.timer.paused = True
        self.katrain.game.current_node.time_used = 0
        self.katrain.game.main_time_used = 0
        self.katrain.update_state()


class NewGamePopup(QuickConfigGui):
    mode = StringProperty("newgame")

    def __init__(self, katrain):
        super().__init__(katrain)
        for bw, info in katrain.players_info.items():
            self.player_setup.update_player_info(bw, info)

        self.rules_spinner.value_refs = [name for abbr, name in katrain.engine.RULESETS_ABBR]
        self.bind(mode=self.update_playername)
        Clock.schedule_once(self.update_from_current_game, 0.1)

    def normalized_rules(self):
        rules = self.katrain.game.root.get_property("RU", "japanese").strip().lower()
        for abbr, name in self.katrain.engine.RULESETS_ABBR:
            if abbr == rules or name == rules:
                return name

    def update_playerinfo(self, *args):
        for bw, player_setup in self.player_setup.players.items():
            name = self.player_name[bw].text
            if name:
                self.katrain.game.root.set_property("P" + bw, name)
            else:
                self.katrain.game.root.clear_property("P" + bw)
            self.katrain.update_player(bw, **player_setup.player_type_dump)

    def update_playername(self, *args):
        for bw in "BW":
            name = self.katrain.game.root.get_property("P" + bw, None)
            if name and SGF_INTERNAL_COMMENTS_MARKER not in name:
                self.player_name[bw].text = name if self.mode == "editgame" else ""

    def update_from_current_game(self, *args):  # set rules and komi
        rules = self.normalized_rules()
        self.km.text = str(self.katrain.game.root.komi)
        if rules is not None:
            self.rules_spinner.select_key(rules.strip())

    def update_config(self, save_to_file=True, close_popup=True):
        super().update_config(save_to_file=save_to_file, close_popup=close_popup)
        props = self.collect_properties(self)
        self.katrain.log(f"Mode: {self.mode}, settings: {self.katrain.config('game')}", OUTPUT_DEBUG)
        self.update_playerinfo()  # type
        if self.mode == "newgame":
            if self.restart.active:
                self.katrain.log("Restarting Engine", OUTPUT_DEBUG)
                self.katrain.engine.restart()
            self.katrain._do_new_game()
        elif self.mode == "editgame":
            root = self.katrain.game.root
            changed = False
            for k, currentval, newval in [
                ("RU", self.normalized_rules(), props["game/rules"]),
                ("KM", root.komi, props["game/komi"]),
            ]:
                if currentval != newval:
                    changed = True
                    self.katrain.log(
                        f"Property {k} changed from {currentval} to {newval}, triggering re-analysis of entire game.",
                        OUTPUT_INFO,
                    )
                    self.katrain.game.root.set_property(k, newval)
            if changed:
                self.katrain.engine.on_new_game()
                self.katrain.game.analyze_all_nodes(analyze_fast=True)
        else:  # setup position
            self.katrain._do_new_game()
            self.katrain("selfplay-setup", props["game/setup_move"], props["game/setup_advantage"])
        self.update_playerinfo()  # name


def wrap_anchor(widget):
    anchor = AnchorLayout()
    anchor.add_widget(widget)
    return anchor


class ConfigTeacherPopup(QuickConfigGui):
    def __init__(self, katrain):
        super().__init__(katrain)
        MDApp.get_running_app().bind(language=self.build_and_set_properties)

    def add_option_widgets(self, widgets):
        for widget in widgets:
            self.options_grid.add_widget(wrap_anchor(widget))

    def build_and_set_properties(self, *_args):
        theme = self.katrain.config("trainer/theme")
        undos = self.katrain.config("trainer/num_undo_prompts")
        thresholds = self.katrain.config("trainer/eval_thresholds")
        savesgfs = self.katrain.config("trainer/save_feedback")
        show_dots = self.katrain.config("trainer/show_dots")

        self.themes_spinner.value_refs = list(Theme.EVAL_COLORS.keys())
        self.options_grid.clear_widgets()

        for k in ["dot color", "point loss threshold", "num undos", "show dots", "save dots"]:
            self.options_grid.add_widget(DescriptionLabel(text=i18n._(k), font_name=i18n.font_name, font_size=dp(17)))

        for i, color, threshold, undo, show_dot, savesgf in list(
            zip(range(len(thresholds)), Theme.EVAL_COLORS[theme], thresholds, undos, show_dots, savesgfs)
        )[::-1]:
            self.add_option_widgets(
                [
                    BackgroundMixin(background_color=color, size_hint=[0.9, 0.9]),
                    LabelledFloatInput(text=str(threshold), input_property=f"trainer/eval_thresholds::{i}"),
                    LabelledFloatInput(text=str(undo), input_property=f"trainer/num_undo_prompts::{i}"),
                    LabelledCheckBox(text=str(show_dot), input_property=f"trainer/show_dots::{i}"),
                    LabelledCheckBox(text=str(savesgf), input_property=f"trainer/save_feedback::{i}"),
                ]
            )
        super().build_and_set_properties()

    def update_config(self, save_to_file=True, close_popup=True):
        super().update_config(save_to_file=save_to_file, close_popup=close_popup)
        self.build_and_set_properties()


class DescriptionLabel(Label):
    pass


class ConfigAIPopup(QuickConfigGui):
    max_options = NumericProperty(6)

    def __init__(self, katrain):
        super().__init__(katrain)
        self.ai_select.value_refs = AI_STRATEGIES_RECOMMENDED_ORDER
        selected_strategies = {p.strategy for p in katrain.players_info.values()}
        config_strategy = list((selected_strategies - {AI_DEFAULT}) or {AI_CONFIG_DEFAULT})[0]
        self.ai_select.select_key(config_strategy)
        self.build_ai_options()
        self.ai_select.bind(text=self.build_ai_options)

    def estimate_rank_from_options(self, *_args):
        strategy = self.ai_select.selected[1]
        try:
            options = self.collect_properties(self)  # [strategy]
        except InputParseError:
            self.estimated_rank_label.text = "??"
            return
        prefix = f"ai/{strategy}/"
        options = {k[len(prefix) :]: v for k, v in options.items() if k.startswith(prefix)}
        dan_rank = ai_rank_estimation(strategy, options)
        self.estimated_rank_label.text = rank_label(dan_rank)

    def build_ai_options(self, *_args):
        strategy = self.ai_select.selected[1]
        mode_settings = self.katrain.config(f"ai/{strategy}")
        self.options_grid.clear_widgets()
        self.help_label.text = i18n._(strategy.replace("ai:", "aihelp:"))
        for k, v in sorted(mode_settings.items(), key=lambda kv: (kv[0] not in AI_KEY_PROPERTIES, kv[0])):
            self.options_grid.add_widget(DescriptionLabel(text=k, size_hint_x=0.275))
            if k in AI_OPTION_VALUES:
                values = AI_OPTION_VALUES[k]
                if values == "bool":
                    widget = LabelledCheckBox(input_property=f"ai/{strategy}/{k}")
                    widget.active = v
                    widget.bind(active=self.estimate_rank_from_options)
                else:
                    if isinstance(values[0], Tuple):  # with descriptions, possibly language-specific
                        fixed_values = [(v, re.sub(r"\[(.*?)]", lambda m: i18n._(m[1]), l)) for v, l in values]
                    else:  # just numbers
                        fixed_values = [(v, str(v)) for v in values]
                    widget = LabelledSelectionSlider(
                        values=fixed_values, input_property=f"ai/{strategy}/{k}", key_option=(k in AI_KEY_PROPERTIES)
                    )
                    widget.set_value(v)
                    widget.textbox.bind(text=self.estimate_rank_from_options)
                self.options_grid.add_widget(wrap_anchor(widget))
            else:
                self.options_grid.add_widget(
                    wrap_anchor(LabelledFloatInput(text=str(v), input_property=f"ai/{strategy}/{k}"))
                )
        for _ in range((self.max_options - len(mode_settings)) * 2):
            self.options_grid.add_widget(Label(size_hint_x=None))
        Clock.schedule_once(self.estimate_rank_from_options)

    def update_config(self, save_to_file=True, close_popup=True):
        super().update_config(save_to_file=save_to_file, close_popup=close_popup)
        self.katrain.update_calculated_ranks()
        Clock.schedule_once(self.katrain.controls.update_players, 0)


class EngineRecoveryPopup(QuickConfigGui):
    error_message = StringProperty("")
    code = ObjectProperty(None)

    def __init__(self, katrain, error_message, code):
        super().__init__(katrain)
        self.error_message = str(error_message)
        self.code = code


class BaseConfigPopup(QuickConfigGui):
    MODEL_ENDPOINTS = {
        "Latest distributed model": "https://katagotraining.org/api/networks/newest_training/",
        "Strongest distributed model": "https://katagotraining.org/api/networks/get_strongest/",
    }
    MODELS = {
        "20 block model": "https://github.com/lightvector/KataGo/releases/download/v1.4.5/g170e-b20c256x2-s5303129600-d1228401921.bin.gz",
        "30 block model": "https://github.com/lightvector/KataGo/releases/download/v1.4.5/g170-b30c320x2-s4824661760-d1229536699.bin.gz",
        "40 block model": "https://github.com/lightvector/KataGo/releases/download/v1.4.5/g170-b40c256x2-s5095420928-d1229425124.bin.gz",
    }
    MODEL_DESC = {
        "Fat 40 block model": "https://d3dndmfyhecmj0.cloudfront.net/g170/neuralnets/g170e-b40c384x2-s2348692992-d1229892979.zip",
        "15 block model": "https://d3dndmfyhecmj0.cloudfront.net/g170/neuralnets/g170e-b15c192-s1672170752-d466197061.bin.gz",
    }

    KATAGOS = {
        "win": {
            "OpenCL v1.11.0": "https://github.com/lightvector/KataGo/releases/download/v1.11.0/katago-v1.11.0-opencl-windows-x64.zip",
            "Eigen AVX2 (Modern CPUs) v1.11.0": "https://github.com/lightvector/KataGo/releases/download/v1.11.0/katago-v1.11.0-eigenavx2-windows-x64.zip",
            "Eigen (CPU, Non-optimized) v1.11.0": "https://github.com/lightvector/KataGo/releases/download/v1.11.0/katago-v1.11.0-eigen-windows-x64.zip",
            "OpenCL v1.11.0 (bigger boards)": "https://github.com/lightvector/KataGo/releases/download/v1.11.0/katago-v1.11.0-opencl-windows-x64+bs29.zip",
        },
        "linux": {
            "OpenCL v1.11.0": "https://github.com/lightvector/KataGo/releases/download/v1.11.0/katago-v1.11.0-opencl-linux-x64.zip",
            "Eigen AVX2 (Modern CPUs) v1.11.0": "https://github.com/lightvector/KataGo/releases/download/v1.11.0/katago-v1.11.0-eigenavx2-linux-x64.zip",
            "Eigen (CPU, Non-optimized) v1.11.0": "https://github.com/lightvector/KataGo/releases/download/v1.11.0/katago-v1.11.0-eigen-linux-x64.zip",
            "OpenCL v1.11.0 (bigger boards)": "https://github.com/lightvector/KataGo/releases/download/v1.11.0/katago-v1.11.0-opencl-linux-x64+bs29.zip",
        },
        "just-descriptions": {
            "CUDA v1.11.0 (Windows)": "https://github.com/lightvector/KataGo/releases/download/v1.11.0/katago-v1.11.0-cuda11.2-windows-x64.zip",
            "CUDA v1.11.0 (Linux)": "https://github.com/lightvector/KataGo/releases/download/v1.11.0/katago-v1.11.0-cuda11.1-linux-x64.zip",
            "Cuda/TensorRT v1.11.0 (Windows)": "https://github.com/lightvector/KataGo/releases/download/v1.11.0/katago-v1.11.0-trt8.2-cuda11.2-windows-x64.zip",
            "Cuda/TensorRT v1.11.0 (Linux)": "https://github.com/lightvector/KataGo/releases/download/v1.11.0/katago-v1.11.0-trt8.2-cuda11.1-linux-x64.zip",
        },
    }

    def __init__(self, katrain):
        super().__init__(katrain)
        self.paths = [self.katrain.config("engine/model"), "katrain/models", DATA_FOLDER]
        self.katago_paths = [self.katrain.config("engine/katago"), DATA_FOLDER]
        self.last_clicked_download_models = 0

    def check_models(self, *args):
        all_models = [self.MODELS, self.MODEL_DESC, self.katrain.config("dist_models", {})]

        def extract_model_file(model):
            try:
                return re.match(r".*/([^/]+)", model)[1].replace(".zip", ".bin.gz")
            except (TypeError, IndexError):
                return None

        def find_description(path):
            file = os.path.split(path)[1]
            file_to_desc = {extract_model_file(model): desc for mods in all_models for desc, model in mods.items()}
            if file in file_to_desc:
                return f"{file_to_desc[file]}  -  {path}"
            else:
                return path

        done = set()
        model_files = []
        distributed_training_models = os.path.expanduser(os.path.join(DATA_FOLDER, "katago_contribute/kata1/models"))
        for path in self.paths + [self.model_path.text, distributed_training_models]:
            path = path.rstrip("/\\")
            if path.startswith("katrain"):
                path = path.replace("katrain", PATHS["PACKAGE"].rstrip("/\\"), 1)
            path = os.path.expanduser(path)
            if not os.path.isdir(path):
                path, _file = os.path.split(path)
            slashpath = path.replace("\\", "/")
            if slashpath in done or not os.path.isdir(path):
                continue
            done.add(slashpath)
            files = [
                f.replace("/", os.path.sep).replace(PATHS["PACKAGE"], "katrain")
                for ftype in ["*.bin.gz", "*.txt.gz"]
                for f in glob.glob(slashpath + "/" + ftype)
                if ".tmp." not in f
            ]
            if files and path not in self.paths:
                self.paths.append(path)  # persistent on paths with models found
            model_files += files

        # no description to bottom
        model_files = sorted(
            [(find_description(path), path) for path in model_files],
            key=lambda descpath: "Z" * 10 + path if descpath[0] == descpath[1] else descpath[0],
        )
        models_available_msg = i18n._("models available").format(num=len(model_files))
        self.model_files.values = [models_available_msg] + [desc for desc, path in model_files]
        self.model_files.value_keys = [""] + [path for desc, path in model_files]
        self.model_files.text = models_available_msg

    def check_katas(self, *args):
        def find_description(path):
            file = os.path.split(path)[1].replace(".exe", "")
            file_to_desc = {
                re.match(r".*/([^/]+)", kg)[1].replace(".zip", ""): desc
                for _, kgs in self.KATAGOS.items()
                for desc, kg in kgs.items()
            }
            if file in file_to_desc:
                return f"{file_to_desc[file]}  -  {path}"
            else:
                return path

        done = set()
        kata_files = []
        for path in self.katago_paths + [self.katago_path.text]:
            path = path.rstrip("/\\")
            if path.startswith("katrain"):
                path = path.replace("katrain", PATHS["PACKAGE"].rstrip("/\\"), 1)
            path = os.path.expanduser(path)
            if not os.path.isdir(path):
                path, _file = os.path.split(path)
            slashpath = path.replace("\\", "/")
            if slashpath in done or not os.path.isdir(path):
                continue
            done.add(slashpath)
            files = [
                f.replace("/", os.path.sep).replace(PATHS["PACKAGE"], "katrain")
                for ftype in ["katago*"]
                for f in glob.glob(slashpath + "/" + ftype)
                if os.path.isfile(f) and not f.endswith(".zip")
            ]
            if files and path not in self.paths:
                self.paths.append(path)  # persistent on paths with models found
            kata_files += files

        kata_files = sorted(
            [(path, find_description(path)) for path in kata_files],
            key=lambda f: ("bs29" in f[0]) * 0.1 - (f[0] != f[1]),
        )
        katas_available_msg = i18n._("katago binaries available").format(num=len(kata_files))
        self.katago_files.values = [katas_available_msg, i18n._("default katago option")] + [
            desc for path, desc in kata_files
        ]
        self.katago_files.value_keys = ["", ""] + [path for path, desc in kata_files]
        self.katago_files.text = katas_available_msg

    def download_models(self, *_largs):
        if time.time() - self.last_clicked_download_models > 5:
            self.last_clicked_download_models = time.time()
            threading.Thread(target=self._download_models, daemon=True).start()

    def _download_models(self):
        def download_complete(req, tmp_path, path, model):
            try:
                os.rename(tmp_path, path)
                self.katrain.log(f"Download of {model} complete -> {path}", OUTPUT_INFO)
            except Exception as e:
                self.katrain.log(f"Download of {model} complete, but could not move file: {e}", OUTPUT_ERROR)
            self.check_models()

        for c in self.download_progress_box.children:
            if isinstance(c, ProgressLoader) and c.request:
                c.request.cancel()
        Clock.schedule_once(lambda _dt: self.download_progress_box.clear_widgets(), -1)  # main thread
        downloading = False

        dist_models = {k: v for k, v in self.katrain.config("dist_models", {}).items() if k in self.MODEL_ENDPOINTS}

        for name, url in self.MODEL_ENDPOINTS.items():
            try:
                http = urllib3.PoolManager()
                response = http.request("GET", url)
                if response.status != 200:
                    raise Exception(
                        f"Request to {url} returned code {response.status} != 200: {response.data.decode()}"
                    )
                dist_models[name] = json.loads(response.data.decode("utf-8"))["model_file"]
            except Exception as e:
                self.katrain.log(f"Failed to retrieve info for model: {e}", OUTPUT_INFO)
        self.katrain._config["dist_models"] = dist_models
        self.katrain.save_config(key="dist_models")

        for name, url in {**self.MODELS, **dist_models}.items():
            filename = os.path.split(url)[1]
            if not any(os.path.split(f)[1] == filename for f in self.model_files.values):
                savepath = os.path.expanduser(os.path.join(DATA_FOLDER, filename))
                savepath_tmp = savepath + ".part"
                self.katrain.log(f"Downloading {name} from {url} to {savepath_tmp}", OUTPUT_INFO)
                Clock.schedule_once(
                    lambda _dt, _savepath=savepath, _savepath_tmp=savepath_tmp, _url=url, _name=name: ProgressLoader(
                        self.download_progress_box,
                        download_url=_url,
                        path_to_file=_savepath_tmp,
                        downloading_text=f"Downloading {_name}: " + "{}",
                        label_downloading_text=f"Starting download for {_name}",
                        download_complete=lambda req, tmp=_savepath_tmp, path=_savepath, model=_name: download_complete(
                            req, tmp, path, model
                        ),
                        download_redirected=lambda req, mname=_name: self.katrain.log(
                            f"Download {mname} redirected {req.resp_headers}", OUTPUT_DEBUG
                        ),
                        download_error=lambda req, error, mname=_name: self.katrain.log(
                            f"Download of {mname} failed or cancelled ({error})", OUTPUT_ERROR
                        ),
                    ),
                    0,
                )  # main thread
                downloading = True
        if not downloading:
            Clock.schedule_once(
                lambda _dt: self.download_progress_box.add_widget(
                    Label(text=i18n._("All models downloaded"), font_name=i18n.font_name, text_size=(None, dp(50)))
                ),
                0,
            )  # main thread

    def download_katas(self, *_largs):
        def unzipped_name(zipfile):
            if platform == "win":
                return zipfile.replace(".zip", ".exe")
            else:
                return zipfile.replace(".zip", "")

        def download_complete(req, tmp_path, path, binary):
            try:
                if tmp_path.endswith(".zip"):
                    with ZipFile(tmp_path, "r") as zipObj:
                        exes = [f for f in zipObj.namelist() if f.startswith("katago")]
                        if len(exes) != 1:
                            raise FileNotFoundError(
                                f"Zip file {tmp_path} does not contain exactly 1 file starting with 'katago' (contents: {zipObj.namelist()})"
                            )
                        with open(path, "wb") as fout:
                            fout.write(zipObj.read(exes[0]))
                            os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP)
                        for f in zipObj.namelist():
                            if f.lower().endswith("dll"):
                                try:
                                    with open(os.path.join(os.path.split(path)[0], f), "wb") as fout:
                                        fout.write(zipObj.read(f))
                                except:  # already there? no problem
                                    pass
                    os.remove(tmp_path)
                else:
                    os.rename(tmp_path, path)
                self.katrain.log(f"Download of katago binary {binary} complete -> {path}", OUTPUT_INFO)
            except Exception as e:
                self.katrain.log(
                    f"Download of katago binary {binary} complete, but could not move file: {e}", OUTPUT_ERROR
                )
            self.check_katas()

        for c in self.katago_download_progress_box.children:
            if isinstance(c, ProgressLoader) and c.request:
                c.request.cancel()
        self.katago_download_progress_box.clear_widgets()
        downloading = False
        for name, url in self.KATAGOS.get(platform, {}).items():
            filename = os.path.split(url)[1]
            exe_name = unzipped_name(filename)
            if not any(os.path.split(f)[1] == exe_name for f in self.katago_files.values):
                savepath_tmp = os.path.expanduser(os.path.join(DATA_FOLDER, filename))
                exe_path_name = os.path.expanduser(os.path.join(DATA_FOLDER, exe_name))
                self.katrain.log(f"Downloading binary {name} from {url} to {savepath_tmp}", OUTPUT_INFO)
                ProgressLoader(
                    root_instance=self.katago_download_progress_box,
                    download_url=url,
                    path_to_file=savepath_tmp,
                    downloading_text=f"Downloading {name}: " + "{}",
                    label_downloading_text=f"Starting download for {name}",
                    download_complete=lambda req, tmp=savepath_tmp, path=exe_path_name, model=name: download_complete(
                        req, tmp, path, model
                    ),
                    download_redirected=lambda req, mname=name: self.katrain.log(
                        f"Download {mname} redirected {req.resp_headers}", OUTPUT_DEBUG
                    ),
                    download_error=lambda req, error, mname=name: self.katrain.log(
                        f"Download of {mname} failed or cancelled ({error})", OUTPUT_ERROR
                    ),
                )
                downloading = True
        if not downloading:
            if not self.KATAGOS.get(platform):
                self.katago_download_progress_box.add_widget(
                    Label(text=f"No binaries available for platform {platform}", text_size=(None, dp(50)))
                )
            else:
                self.katago_download_progress_box.add_widget(
                    Label(text=i18n._("All binaries downloaded"), font_name=i18n.font_name, text_size=(None, dp(50)))
                )


class ConfigPopup(BaseConfigPopup):
    def __init__(self, katrain):
        super().__init__(katrain)
        Clock.schedule_once(self.check_katas)
        MDApp.get_running_app().bind(language=self.check_models)
        MDApp.get_running_app().bind(language=self.check_katas)

    def update_config(self, save_to_file=True, close_popup=True):
        updated = super().update_config(save_to_file=save_to_file, close_popup=close_popup)
        self.katrain.debug_level = self.katrain.config("general/debug_level", OUTPUT_INFO)

        ignore = {"max_visits", "fast_visits", "max_time", "enable_ownership", "wide_root_noise"}
        detected_restart = [key for key in updated if "engine" in key and not any(ig in key for ig in ignore)]
        if detected_restart:

            def restart_engine(_dt):
                self.katrain.controls.set_status("", STATUS_INFO)
                self.katrain.log(f"Restarting Engine after {detected_restart} settings change")
                self.katrain.controls.set_status(i18n._("restarting engine"), STATUS_INFO)

                old_engine = self.katrain.engine  # type: KataGoEngine
                old_proc = old_engine.katago_process
                if old_proc:
                    old_engine.shutdown(finish=False)
                new_engine = KataGoEngine(self.katrain, self.katrain.config("engine"))
                self.katrain.engine = new_engine
                self.katrain.game.engines = {"B": new_engine, "W": new_engine}
                self.katrain.game.analyze_all_nodes(
                    analyze_fast=True
                )  # old engine was possibly broken, so make sure we redo any failures
                self.katrain.update_state()

            Clock.schedule_once(restart_engine, 0)


class ContributePopup(BaseConfigPopup):
    def __init__(self, katrain):
        super().__init__(katrain)
        MDApp.get_running_app().bind(language=self.check_katas)
        Clock.schedule_once(self.check_katas)

    def start_contributing(self):
        self.update_config(True, close_popup=False)
        self.error.text = ""
        log_settings = {**self.katrain.config("contribute"), "password": "***"}
        self.katrain.log(f"Updating contribution settings {log_settings}", OUTPUT_DEBUG)
        if not self.katrain.config("contribute/username") or not self.katrain.config("contribute/password"):
            self.error.text = "Please enter your username and password for katagotraining.org"
        else:
            self.popup.dismiss()
            self.katrain("katago-contribute")


class LoadSGFPopup(BaseConfigPopup):
    def __init__(self, katrain):
        super().__init__(katrain)
        app = MDApp.get_running_app()
        self.filesel.favorites = [
            (os.path.abspath(app.gui.config("general/sgf_load")), "Last Load Dir"),
            (os.path.abspath(app.gui.config("general/sgf_save")), "Last Save Dir"),
        ]
        self.filesel.path = os.path.abspath(os.path.expanduser(app.gui.config("general/sgf_load")))
        self.filesel.select_string = "Load File"

    def on_submit(self):
        self.filesel.button_clicked()


class SaveSGFPopup(BoxLayout):
    def __init__(self, suggested_filename, **kwargs):
        super().__init__(**kwargs)
        self.suggested_filename = suggested_filename
        app = MDApp.get_running_app()
        self.filesel.favorites = [
            (os.path.abspath(app.gui.config("general/sgf_load")), "Last Load Dir"),
            (os.path.abspath(app.gui.config("general/sgf_save")), "Last Save Dir"),
        ]
        save_path = os.path.expanduser(MDApp.get_running_app().gui.config("general/sgf_save") or ".")

        def set_suggested(_widget, path):
            self.filesel.ids.file_text.text = os.path.join(path, self.suggested_filename)

        self.filesel.ids.list_view.bind(path=set_suggested)
        self.filesel.path = os.path.abspath(save_path)
        self.filesel.select_string = "Save File"

    def on_submit(self):
        self.filesel.button_clicked()


class ReAnalyzeGamePopup(BoxLayout):
    katrain = ObjectProperty(None)
    popup = ObjectProperty(None)

    def on_submit(self):
        self.button.trigger_action(duration=0)


class TsumegoFramePopup(BoxLayout):
    katrain = ObjectProperty(None)
    popup = ObjectProperty(None)

    def on_submit(self):
        self.button.trigger_action(duration=0)


class GameReportPopup(BoxLayout):
    def __init__(self, katrain, **kwargs):
        super().__init__(**kwargs)
        self.katrain = katrain
        self.depth_filter = None
        Clock.schedule_once(self._refresh, 0)

    def set_depth_filter(self, filter):
        self.depth_filter = filter
        Clock.schedule_once(self._refresh, 0)

    def _refresh(self, _dt=0):
        game = self.katrain.game
        thresholds = self.katrain.config("trainer/eval_thresholds")

        sum_stats, histogram, player_ptloss = game_report(game, depth_filter=self.depth_filter, thresholds=thresholds)
        labels = [f"≥ {pt}" if pt > 0 else f"< {thresholds[-2]}" for pt in thresholds]

        table = GridLayout(cols=3, rows=6 + len(thresholds))
        colors = [
            [cp * 0.75 for cp in col[:3]] + [1] for col in Theme.EVAL_COLORS[self.katrain.config("trainer/theme")]
        ]

        table.add_widget(TableHeaderLabel(text="", background_color=Theme.BACKGROUND_COLOR))
        table.add_widget(TableHeaderLabel(text=i18n._("header:keystats"), background_color=Theme.BACKGROUND_COLOR))
        table.add_widget(TableHeaderLabel(text="", background_color=Theme.BACKGROUND_COLOR))

        for i, (label, fmt, stat, scale, more_is_better) in enumerate(
            [
                ("accuracy", "{:.1f}", "accuracy", 100, True),
                ("meanpointloss", "{:.1f}", "mean_ptloss", 5, False),
                ("aitopmove", "{:.1%}", "ai_top_move", 1, True),
                ("aitop5", "{:.1%}", "ai_top5_move", 1, True),
            ]
        ):

            statcell = {
                bw: TableStatLabel(
                    text=fmt.format(sum_stats[bw][stat]) if stat in sum_stats[bw] else "",
                    side=side,
                    value=sum_stats[bw].get(stat, 0),
                    scale=scale,
                    bar_color=Theme.STAT_BETTER_COLOR
                    if (sum_stats[bw].get(stat, 0) < sum_stats[Move.opponent_player(bw)].get(stat, 0)) ^ more_is_better
                    else Theme.STAT_WORSE_COLOR,
                    background_color=Theme.BOX_BACKGROUND_COLOR,
                )
                for (bw, side) in zip("BW", ["left", "right"])
            }
            table.add_widget(statcell["B"])
            table.add_widget(TableCellLabel(text=i18n._(f"stat:{label}"), background_color=Theme.BOX_BACKGROUND_COLOR))
            table.add_widget(statcell["W"])

        table.add_widget(TableHeaderLabel(text=i18n._("header:num moves"), background_color=Theme.BACKGROUND_COLOR))
        table.add_widget(TableHeaderLabel(text=i18n._("stats:pointslost"), background_color=Theme.BACKGROUND_COLOR))
        table.add_widget(TableHeaderLabel(text=i18n._("header:num moves"), background_color=Theme.BACKGROUND_COLOR))

        for i, (col, label, pt) in enumerate(zip(colors[::-1], labels[::-1], thresholds[::-1])):
            statcell = {
                bw: TableStatLabel(
                    text=str(histogram[i][bw]),
                    side=side,
                    value=histogram[i][bw],
                    scale=len(player_ptloss[bw]) + 1e-6,
                    bar_color=col,
                    background_color=Theme.BOX_BACKGROUND_COLOR,
                )
                for (bw, side) in zip("BW", ["left", "right"])
            }
            table.add_widget(statcell["B"])
            table.add_widget(TableCellLabel(text=label, background_color=col))
            table.add_widget(statcell["W"])

        self.stats.clear_widgets()
        self.stats.add_widget(table)

        for bw, player_info in self.katrain.players_info.items():
            self.player_infos[bw].player_type = player_info.player_type
            self.player_infos[bw].captures = ""  # ;)
            self.player_infos[bw].player_subtype = player_info.player_subtype
            self.player_infos[bw].name = player_info.name
            self.player_infos[bw].rank = (
                player_info.sgf_rank
                if player_info.player_type == PLAYER_HUMAN
                else rank_label(player_info.calculated_rank)
            )

        # if not done analyzing, check again in 1s
        if not self.katrain.engine.is_idle():
            Clock.schedule_once(self._refresh, 1)
