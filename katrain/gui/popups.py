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
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.utils import platform
from kivy.app import App
from kivy.uix.checkbox import CheckBox

from katrain.gui.kivyutils import KaTrainTextInput

from katrain.core.ai import ai_rank_estimation
from katrain.core.constants import (
    AI_CONFIG_DEFAULT,
    AI_DEFAULT,
    AI_HUMAN,
    AI_KEY_PROPERTIES,
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
    KeyValueSpinner,
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
from katrain.gui.components.buttons import KtButton
from katrain.gui.components.forms import KtFormRow, KtNumberField, KtTextField
from katrain.gui.components.layout import KtCard, KtColumn, KtDivider, KtRow


class InputParseError(Exception):
    pass


class BoundForm:
    """Explicit registry of input widgets keyed by `input_property`.

    This replaces the previous implicit widget-tree traversal during save/apply.
    """

    def __init__(self):
        self._widgets: dict[str, Any] = {}

    def register(self, widget: Any) -> None:
        key = getattr(widget, "input_property", "")
        if not key:
            return
        self._widgets[key] = widget

    def values(self) -> dict[str, Any]:
        ret: dict[str, Any] = {}
        for key, widget in self._widgets.items():
            try:
                ret[key] = widget.input_value
            except Exception as e:
                raise InputParseError(
                    f"Could not parse value '{widget.raw_input_value}' for {key} ({widget.__class__.__name__}): {e}"
                )
        return ret


class I18NPopup(Popup):
    title_key = StringProperty("")
    font_name = StringProperty(Theme.DEFAULT_FONT)

    def __init__(self, size=None, **kwargs):
        if size:  # do not exceed window size
            app = App.get_running_app()
            size[0] = min(app.gui.width, size[0])
            size[1] = min(app.gui.height, size[1])
        super().__init__(size=size, **kwargs)
        self.bind(on_dismiss=Clock.schedule_once(lambda _dt: App.get_running_app().gui.update_state(), 1))


def _get_config_path(config: dict[str, Any], path: str) -> Any:
    cur: Any = config
    for k in path.split("/"):
        cur = cur[k]
    return cur


def _set_config_path(config: dict[str, Any], path: str, value: Any) -> None:
    keys = path.split("/")
    cur: Any = config
    for k in keys[:-1]:
        if k not in cur or not isinstance(cur[k], dict):
            cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value


class PopupContent(BoxLayout):
    """Popup content base with a back-reference to its Popup wrapper."""

    popup = ObjectProperty(None)


class LabelledTextInput(KaTrainTextInput):
    input_property = StringProperty("")
    multiline = BooleanProperty(False)
    _registered = BooleanProperty(False)

    def on_parent(self, *_args):
        if self._registered:
            return
        parent = self.parent
        while parent is not None and not isinstance(parent, QuickConfigGui):
            parent = getattr(parent, "parent", None)
        if parent is not None:
            parent.register_input_widget(self)
            self._registered = True

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


class LabelledCheckBox(CheckBox):
    input_property = StringProperty("")
    _registered = BooleanProperty(False)

    def __init__(self, text=None, **kwargs):
        if text is not None:
            kwargs["active"] = text.lower() == "true"
        super().__init__(**kwargs)

    def on_parent(self, *_args):
        if self._registered:
            return
        parent = self.parent
        while parent is not None and not isinstance(parent, QuickConfigGui):
            parent = getattr(parent, "parent", None)
        if parent is not None:
            parent.register_input_widget(self)
            self._registered = True

    @property
    def input_value(self):
        return bool(self.active)

    def raw_input_value(self):
        return self.active


class LabelledSpinner(I18NSpinner):
    input_property = StringProperty("")
    _registered = BooleanProperty(False)

    @property
    def input_value(self):
        return self.selected[1]  # ref value

    def on_parent(self, *_args):
        if self._registered:
            return
        parent = self.parent
        while parent is not None and not isinstance(parent, QuickConfigGui):
            parent = getattr(parent, "parent", None)
        if parent is not None:
            parent.register_input_widget(self)
            self._registered = True

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
    _registered = BooleanProperty(False)

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

    def on_parent(self, *_args):
        if self._registered:
            return
        parent = self.parent
        while parent is not None and not isinstance(parent, QuickConfigGui):
            parent = getattr(parent, "parent", None)
        if parent is not None:
            parent.register_input_widget(self)
            self._registered = True


class QuickConfigGui(BoxLayout):
    def __init__(self, katrain):
        # KV rules for subclasses may create children that immediately call `on_parent`
        # to register themselves with the nearest `QuickConfigGui`. Ensure `form` exists
        # *before* Kivy applies KV rules during `super().__init__()`.
        self.katrain = katrain
        self.popup = None
        self.form = BoundForm()
        super().__init__()
        Clock.schedule_once(self.build_and_set_properties, 0)

    def register_input_widget(self, widget: Any) -> None:
        self.form.register(widget)

    def collect_properties(self, _widget=None) -> Dict:
        # No widget-tree traversal: values come from explicit registration.
        return self.form.values()

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


class NewGamePopup(PopupContent):
    __no_builder__ = True

    mode = StringProperty("newgame")

    def __init__(self, katrain, **kwargs):
        super().__init__(**kwargs)
        self.katrain = katrain
        self.orientation = "vertical"
        self.spacing = dp(Theme.CP_SPACING)
        self.padding = [dp(Theme.CP_PADDING)] * 4

        # Player setup block is already a reusable Python widget.
        from katrain.gui.kivyutils import PlayerSetupBlock

        self.player_setup = PlayerSetupBlock(update_global=False, katrain=katrain)

        self._size = KtTextField(multiline=False)
        self._komi = KtNumberField(number_type="float", multiline=False)
        self._handicap = KtNumberField(number_type="int", multiline=False)
        self._rules = I18NSpinner(size_hint_y=None, height=dp(44))
        self._clear_cache = CheckBox(active=bool(self.katrain.config("game/clear_cache", False)), size_hint=(None, None))
        self._clear_cache.size = (dp(32), dp(32))

        self._rules.value_refs = [name for _abbr, name in katrain.engine.RULESETS_ABBR]

        form = KtCard()
        form.add_widget(self._row("board size", self._size))
        form.add_widget(self._row("komi", self._komi))
        form.add_widget(self._row("handicap", self._handicap))
        form.add_widget(self._row("ruleset", self._rules))
        form.add_widget(self._row("clear cache", self._clear_cache))

        scroll = ScrollView(do_scroll_x=False)
        content = KtColumn(size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))
        content.add_widget(self.player_setup)
        content.add_widget(form)
        scroll.add_widget(content)
        self.add_widget(scroll)

        self.add_widget(KtDivider())

        buttons = KtRow(padding=[0, 0, 0, 0], size_hint_y=None, height=dp(48))
        buttons.add_widget(KtButton(text="Cancel", on_click=self._dismiss))
        buttons.add_widget(KtButton(text_key="newgame", variant="primary", on_click=self.apply))
        self.add_widget(buttons)

        Clock.schedule_once(lambda _dt: self.update_from_current_game(), 0)

    def _dismiss(self):
        if self.popup:
            self.popup.dismiss()

    def _row(self, label_key: str, field_widget):
        row = KtFormRow(label_key=label_key)
        row.set_field(field_widget)
        return row

    def update_from_current_game(self, *_args):
        # Initialize fields from current config/game.
        self._size.value = str(self.katrain.config("game/size", "19"))
        self._komi.value = str(self.katrain.config("game/komi", 6.5))
        self._handicap.value = str(self.katrain.config("game/handicap", 0))

        if self.katrain.game and self.katrain.game.root:
            rules = self.katrain.game.root.get_property("RU", self.katrain.config("game/rules", "japanese"))
            rules = (rules or "").strip()
            if rules:
                self._rules.select_key(rules)

        for bw, info in self.katrain.players_info.items():
            self.player_setup.players[bw].update_widget(info.player_type, info.player_subtype)

    def apply(self):
        _set_config_path(self.katrain._config, "game/size", self._size.value.strip() or "19")
        _set_config_path(self.katrain._config, "game/komi", float(self._komi.value or "0"))
        _set_config_path(self.katrain._config, "game/handicap", int(self._handicap.value or "0"))
        _set_config_path(self.katrain._config, "game/rules", self._rules.selected[1] or "japanese")
        _set_config_path(self.katrain._config, "game/clear_cache", bool(self._clear_cache.active))
        self.katrain.save_config("game")

        # Update players.
        for bw, player_setup in self.player_setup.players.items():
            self.katrain.update_player(bw, **player_setup.player_type_dump)

        self._dismiss()
        self.katrain._do_new_game()


def wrap_anchor(widget):
    anchor = AnchorLayout()
    anchor.add_widget(widget)
    return anchor


class ConfigTeacherPopup(QuickConfigGui):
    __no_builder__ = True

    def __init__(self, katrain):
        super().__init__(katrain)
        self.clear_widgets()
        self.orientation = "vertical"
        self.spacing = dp(Theme.CP_SPACING)
        self.padding = [dp(Theme.CP_PADDING)] * 4

        body_scroll = ScrollView(do_scroll_x=False)
        body = KtColumn(size_hint_y=None, padding=[0, 0, 0, 0])
        body.bind(minimum_height=body.setter("height"))

        # Main trainer toggles.
        self._trainer_rows = KtCard()
        self._themes_spinner = I18NSpinner(size_hint_y=None, height=dp(44))
        self._themes_spinner.bind(text=lambda *_: self._on_theme_changed())

        self._low_visits = LabelledIntInput(input_property="trainer/low_visits")
        self._eval_on_show_last = LabelledIntInput(input_property="trainer/eval_on_show_last")
        self._eval_show_ai = LabelledCheckBox(input_property="trainer/eval_show_ai")
        self._extra_precision = LabelledCheckBox(input_property="trainer/extra_precision")

        self._trainer_rows.add_widget(self._row("theme", self._themes_spinner))
        self._trainer_rows.add_widget(self._row("show stats if", self._low_visits))
        self._trainer_rows.add_widget(self._row("show last n dots", self._eval_on_show_last))
        self._trainer_rows.add_widget(self._row("show ai dots", self._eval_show_ai))
        self._trainer_rows.add_widget(self._row("show two digits for point loss near zero", self._extra_precision))

        body.add_widget(self._trainer_rows)

        # Threshold/dots table.
        self.options_grid = GridLayout(
            cols=4,
            size_hint_y=None,
            spacing=dp(Theme.CP_SMALL_SPACING),
            row_force_default=True,
            row_default_height=dp(40),
        )
        self.options_grid.bind(minimum_height=self.options_grid.setter("height"))
        table = KtCard()
        table.add_widget(self.options_grid)
        body.add_widget(table)

        body_scroll.add_widget(body)
        self.add_widget(body_scroll)

        self.add_widget(KtDivider())

        buttons = KtRow(padding=[0, 0, 0, 0], size_hint_y=None, height=dp(48))
        buttons.add_widget(KtButton(text="Cancel", on_click=lambda: self.popup.dismiss() if self.popup else None))
        buttons.add_widget(KtButton(text_key="update teacher", variant="primary", on_click=lambda: self.update_config(True)))
        self.add_widget(buttons)

        Clock.schedule_once(lambda _dt: self.build_and_set_properties(), 0)

    def _row(self, label_key: str, field_widget):
        row = KtFormRow(label_key=label_key)
        row.set_field(field_widget)
        return row

    @property
    def themes_spinner(self):
        return self._themes_spinner

    def _on_theme_changed(self):
        # Persist theme choice immediately (and rebuild the colored table).
        selected = self._themes_spinner.selected[1]
        if selected:
            self.katrain._config["trainer"]["theme"] = selected
            self.katrain.save_config("trainer")
        self.build_and_set_properties()

    def add_option_widgets(self, widgets):
        for widget in widgets:
            self.options_grid.add_widget(wrap_anchor(widget))

    def build_and_set_properties(self, *_args):
        theme = self.katrain.config("trainer/theme")
        undos = self.katrain.config("trainer/num_undo_prompts")
        thresholds = self.katrain.config("trainer/eval_thresholds")
        show_dots = self.katrain.config("trainer/show_dots")

        self.themes_spinner.value_refs = list(Theme.EVAL_COLORS.keys())
        self.themes_spinner.select_key(theme)
        self.options_grid.clear_widgets()

        for k in ["dot color", "point loss threshold", "num undos", "show dots"]:
            self.options_grid.add_widget(DescriptionLabel(text=i18n._(k), font_name=i18n.font_name, font_size=dp(17)))

        for i, color, threshold, undo, show_dot in list(
            zip(range(len(thresholds)), Theme.EVAL_COLORS[theme], thresholds, undos, show_dots)
        )[::-1]:
            self.add_option_widgets(
                [
                    BackgroundMixin(background_color=color, size_hint=[0.9, 0.9]),
                    LabelledFloatInput(text=str(threshold), input_property=f"trainer/eval_thresholds::{i}"),
                    LabelledFloatInput(text=str(undo), input_property=f"trainer/num_undo_prompts::{i}"),
                    LabelledCheckBox(text=str(show_dot), input_property=f"trainer/show_dots::{i}"),
                ]
            )
        super().build_and_set_properties()

    def update_config(self, save_to_file=True, close_popup=True):
        super().update_config(save_to_file=save_to_file, close_popup=close_popup)
        self.build_and_set_properties()


class DescriptionLabel(Label):
    pass


class ConfigAIPopup(PopupContent):
    __no_builder__ = True

    def __init__(self, katrain, **kwargs):
        super().__init__(**kwargs)
        self.katrain = katrain
        self.orientation = "vertical"
        self.spacing = dp(Theme.CP_SPACING)
        self.padding = [dp(Theme.CP_PADDING)] * 4

        self._strategy_select = I18NSpinner(size_hint_y=None, height=dp(44))
        self._strategy_select.value_refs = AI_STRATEGIES_RECOMMENDED_ORDER

        selected_strategies = {p.strategy for p in katrain.players_info.values()}
        config_strategy = list((selected_strategies - {AI_DEFAULT}) or {AI_CONFIG_DEFAULT})[0]
        self._strategy_select.select_key(config_strategy)
        self._strategy_select.bind(text=lambda *_: self._rebuild_options())

        top = KtCard(orientation="vertical", size_hint_y=None)
        top.bind(minimum_height=top.setter("height"))
        top.add_widget(self._row("ai settings", self._strategy_select))

        self._estimated = Label(text="?", color=Theme.TEXT_COLOR, size_hint_y=None, height=dp(30))
        top.add_widget(self._estimated)

        self.add_widget(top)

        self._options_scroll = ScrollView(do_scroll_x=False)
        self._options_box = KtColumn(size_hint_y=None)
        self._options_box.bind(minimum_height=self._options_box.setter("height"))
        self._options_scroll.add_widget(self._options_box)
        self.add_widget(self._options_scroll)

        self.add_widget(KtDivider())

        buttons = KtRow(padding=[0, 0, 0, 0], size_hint_y=None, height=dp(48))
        buttons.add_widget(KtButton(text="Cancel", on_click=self._dismiss))
        buttons.add_widget(KtButton(text="Update", variant="primary", on_click=self.apply))
        self.add_widget(buttons)

        # v2: keep AI settings UI explicitly curated, rather than dumping raw config keys.
        self._last_strategy = None
        self._suspend_callbacks = False

        self._human_profile = KeyValueSpinner(size_hint_y=None, height=dp(44))
        self._human_profile.values = ["Rank-based", "Pro-year"]
        self._human_profile.value_refs = ["rank", "proyear"]
        self._human_profile.bind(selected_index=lambda *_: self._on_human_profile_changed())

        # Human rank is stored as kyu-rank style int where:
        #   1..20 => 1k..20k
        #   0,-1,-2,... => 1d,2d,3d,...
        rank_value_refs: list[int] = list(range(20, 0, -1)) + list(range(0, -8, -1))
        rank_values: list[str] = [f"{k}k" for k in range(20, 0, -1)] + [f"{d}d" for d in range(1, 9)]
        self._human_rank = KeyValueSpinner(size_hint_y=None, height=dp(44))
        self._human_rank.values = rank_values
        self._human_rank.value_refs = rank_value_refs
        self._human_rank.bind(selected_index=lambda *_: self._on_human_option_changed())

        self._human_modern_style = CheckBox(active=False, size_hint=(None, None))
        self._human_modern_style.size = (dp(32), dp(32))
        self._human_modern_style.bind(active=lambda *_: self._on_human_option_changed())

        self._human_pro_year = KtNumberField(number_type="int", multiline=False)
        self._human_pro_year.bind(value=lambda *_: self._on_human_option_changed())

        self._hint = Label(
            text="",
            color=Theme.TEXT_COLOR,
            font_name=i18n.font_name,
            font_size=sp(Theme.DESC_FONT_SIZE),
            halign="left",
            valign="top",
            text_size=(None, None),
            size_hint_y=None,
            height=dp(50),
        )

        self._rebuild_options()

    def _dismiss(self):
        if self.popup:
            self.popup.dismiss()

    def _row(self, label_key: str, field_widget):
        row = KtFormRow(label_key=label_key)
        row.set_field(field_widget)
        return row

    def _on_human_profile_changed(self, *_args) -> None:
        if self._suspend_callbacks:
            return
        self._rebuild_options()

    def _on_human_option_changed(self, *_args) -> None:
        if self._suspend_callbacks:
            return
        self._update_estimate()

    def _load_human_from_config(self) -> None:
        settings = dict(self.katrain.config(f"ai/{AI_HUMAN}") or {})
        profile = str(settings.get("profile") or "").strip()
        if not profile:
            profile = "proyear" if "pro_year" in settings else "rank"

        self._suspend_callbacks = True
        try:
            self._human_profile.select_key(profile)
            try:
                self._human_rank.select_key(int(round(settings.get("human_kyu_rank", 8))))
            except Exception:
                self._human_rank.select_key(8)
            self._human_modern_style.active = bool(settings.get("modern_style", False))
            try:
                self._human_pro_year.value = str(int(round(settings.get("pro_year", 1914))))
            except Exception:
                self._human_pro_year.value = "1914"
        finally:
            self._suspend_callbacks = False

    def _current_ai_options(self, strategy: str) -> dict[str, Any]:
        if strategy == AI_DEFAULT:
            return {}

        if strategy == AI_HUMAN:
            profile = self._human_profile.selected[1] or "rank"
            try:
                human_rank = int(self._human_rank.selected[1])
            except Exception:
                human_rank = 8
            try:
                pro_year = int(self._human_pro_year.value or "1914")
            except Exception:
                pro_year = 1914
            return {
                "profile": profile,
                "human_kyu_rank": human_rank,
                "modern_style": bool(self._human_modern_style.active),
                "pro_year": pro_year,
            }

        return dict(self.katrain.config(f"ai/{strategy}") or {})

    def _rebuild_options(self):
        self._options_box.clear_widgets()
        # Widgets can remain parented to a row that we just removed from `_options_box`.
        # Detach before re-adding to avoid "already has a parent" WidgetException.
        for w in (self._human_profile, self._human_rank, self._human_modern_style, self._human_pro_year, self._hint):
            if w.parent:
                w.parent.remove_widget(w)

        strategy = self._strategy_select.selected[1]
        if strategy != self._last_strategy:
            if strategy == AI_HUMAN:
                self._load_human_from_config()
            self._last_strategy = strategy

        self._hint.text = ""
        self._hint.height = 1

        if strategy == AI_DEFAULT:
            self._options_box.add_widget(
                Label(
                    text="No AI options here. Use General & Engine Settings to change KataGo model, config, and visits.",
                    color=Theme.TEXT_COLOR,
                    font_name=i18n.font_name,
                    font_size=sp(Theme.DESC_FONT_SIZE),
                    halign="left",
                    valign="top",
                    text_size=(dp(680), None),
                    size_hint_y=None,
                    height=dp(60),
                )
            )
            self._update_estimate()
            return

        if strategy == AI_HUMAN:
            self._options_box.add_widget(self._row("Profile", self._human_profile))

            profile = self._human_profile.selected[1] or "rank"
            if profile == "rank":
                self._options_box.add_widget(self._row("Rank", self._human_rank))
                self._options_box.add_widget(self._row("Modern style", self._human_modern_style))
                self._hint.text = "Rank-based profile uses your chosen rank and modern/pre-AZ style."
            else:
                self._options_box.add_widget(self._row("Year", self._human_pro_year))
                self._hint.text = "Pro-year profile ignores rank and plays like historical pro games around that year."

            if self._hint.text:
                self._hint.height = dp(40)
                self._options_box.add_widget(self._hint)

            self._update_estimate()
            return

        self._options_box.add_widget(
            Label(
                text="Unsupported strategy.",
                color=Theme.TEXT_COLOR,
                font_name=i18n.font_name,
                font_size=sp(Theme.DESC_FONT_SIZE),
                size_hint_y=None,
                height=dp(30),
            )
        )
        self._update_estimate()

    def _update_estimate(self, *_args):
        strategy = self._strategy_select.selected[1]
        options = self._current_ai_options(strategy)
        dan_rank = ai_rank_estimation(strategy, options)
        if dan_rank is None:
            self._estimated.text = f"{i18n._('estimated strength')}: n/a"
        else:
            self._estimated.text = f"{i18n._('estimated strength')}: {rank_label(dan_rank)}"

    def apply(self):
        strategy = self._strategy_select.selected[1]
        if strategy == AI_DEFAULT:
            self._dismiss()
            return

        options = self._current_ai_options(strategy)
        self.katrain._config.setdefault("ai", {})
        self.katrain._config["ai"].setdefault(strategy, {}).update(options)

        self.katrain.save_config("ai")
        self.katrain.update_calculated_ranks()
        Clock.schedule_once(self.katrain.controls.update_players, 0)
        self._dismiss()


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
        "old 15 block model": "https://github.com/lightvector/KataGo/releases/download/v1.3.2/g170e-b15c192-s1672170752-d466197061.txt.gz",
        "Human-like model": "https://github.com/lightvector/KataGo/releases/download/v1.15.0/b18c384nbt-humanv0.bin.gz",
    }
    MODEL_DESC = {
        "Fat 40 block model": "https://d3dndmfyhecmj0.cloudfront.net/g170/neuralnets/g170e-b40c384x2-s2348692992-d1229892979.zip",
        "Recommended 18b model": "https://media.katagotraining.org/uploaded/networks/models/kata1/kata1-b18c384nbt-s9996604416-d4316597426.bin.gz",
        "old 20 block model": "https://github.com/lightvector/KataGo/releases/download/v1.4.5/g170e-b20c256x2-s5303129600-d1228401921.bin.gz",
        "old 30 block model": "https://github.com/lightvector/KataGo/releases/download/v1.4.5/g170-b30c320x2-s4824661760-d1229536699.bin.gz",
        "old 40 block model": "https://github.com/lightvector/KataGo/releases/download/v1.4.5/g170-b40c256x2-s5095420928-d1229425124.bin.gz",
    }

    KATAGOS = {
        "win": {
            "OpenCL v1.16.0": "https://github.com/lightvector/KataGo/releases/download/v1.16.0/katago-v1.16.0-opencl-windows-x64.zip",
            "Eigen AVX2 (Modern CPUs) v1.16.0": "https://github.com/lightvector/KataGo/releases/download/v1.16.0/katago-v1.16.0-eigenavx2-windows-x64.zip",
            "Eigen (CPU, Non-optimized) v1.16.0": "https://github.com/lightvector/KataGo/releases/download/v1.16.0/katago-v1.16.0-eigen-windows-x64.zip",
            "OpenCL v1.16.0 (bigger boards)": "https://github.com/lightvector/KataGo/releases/download/v1.16.0/katago-v1.16.0-opencl-windows-x64+bs50.zip",
        },
        "linux": {
            "OpenCL v1.16.0": "https://github.com/lightvector/KataGo/releases/download/v1.16.0/katago-v1.16.0-opencl-linux-x64.zip",
            "Eigen AVX2 (Modern CPUs) v1.16.0": "https://github.com/lightvector/KataGo/releases/download/v1.16.0/katago-v1.16.0-eigenavx2-linux-x64.zip",
            "Eigen (CPU, Non-optimized) v1.16.0": "https://github.com/lightvector/KataGo/releases/download/v1.16.0/katago-v1.16.0-eigen-linux-x64.zip",            
            "OpenCL v1.16.0 (bigger boards)": "https://github.com/lightvector/KataGo/releases/download/v1.16.0/katago-v1.16.0-opencl-linux-x64+bs50.zip",
        },
        "just-descriptions": {},
    }

    def __init__(self, katrain):
        super().__init__(katrain)
        self.paths = [self.katrain.config("engine/model"), self.katrain.config("engine/humanlike_model"), "katrain/models", DATA_FOLDER]
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
        humanlike_model_files = []
        distributed_training_models = os.path.expanduser(os.path.join(DATA_FOLDER, "katago_contribute/kata1/models"))
        for path in self.paths + [self.model_path.text, self.humanlike_model_path.text, distributed_training_models]:
            path = (path or "").rstrip("/\\")
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
            for file in files:
                if "human" in file:
                    humanlike_model_files.append(file)

        # no description to bottom
        model_files = sorted(
            [(find_description(path), path) for path in model_files],
            key=lambda descpath: ("Recommended" not in descpath[0], "  -  " not in descpath[0], descpath[0]),
        )
        models_available_msg = i18n._("models available").format(num=len(model_files))
        self.model_files.values = [models_available_msg] + [desc for desc, path in model_files]
        self.model_files.value_keys = [""] + [path for desc, path in model_files]
        self.model_files.text = models_available_msg

        humanlike_model_files = sorted(
            [(find_description(path), path) for path in humanlike_model_files],
            key=lambda descpath: ("Recommended" not in descpath[0], "  -  " not in descpath[0], descpath[0]),
        )
        humanlike_models_available_msg = i18n._("models available").format(num=len(humanlike_model_files))
        self.humanlike_model_files.values = [humanlike_models_available_msg] + [desc for desc, path in humanlike_model_files]
        self.humanlike_model_files.value_keys = [""] + [path for desc, path in humanlike_model_files]
        self.humanlike_model_files.text = humanlike_models_available_msg

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
            if not any(os.path.split(f)[1] == filename for f in self.model_files.values + self.humanlike_model_files.values):
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


class ConfigPopup(PopupContent):
    __no_builder__ = True

    def __init__(self, katrain, **kwargs):
        super().__init__(**kwargs)
        self.katrain = katrain
        self.orientation = "vertical"
        self.spacing = dp(Theme.CP_SPACING)
        self.padding = [dp(Theme.CP_PADDING)] * 4

        self._engine_model = KtTextField(multiline=False)
        self._engine_human_model = KtTextField(multiline=False)
        self._engine_katago = KtTextField(multiline=False)
        self._engine_config = KtTextField(multiline=False)
        self._engine_altcommand = KtTextField(multiline=False)
        self._engine_max_visits = KtNumberField(number_type="int", multiline=False)
        self._engine_fast_visits = KtNumberField(number_type="int", multiline=False)
        self._engine_max_time = KtNumberField(number_type="float", multiline=False)
        self._engine_wide_root_noise = KtNumberField(number_type="float", multiline=False)

        self._ui_restore_size = CheckBox(active=bool(self.katrain.config("ui_state/restoresize", True)), size_hint=(None, None))
        self._ui_restore_size.size = (dp(32), dp(32))

        self._general_anim_pv_time = KtNumberField(number_type="float", multiline=False)
        self._general_debug_level = KtNumberField(number_type="int", multiline=False)
        self._sound_enabled = CheckBox(active=bool(self.katrain.config("general/sound", True)), size_hint=(None, None))
        self._sound_enabled.size = (dp(32), dp(32))

        # Load values from current config.
        self._engine_model.value = str(self.katrain.config("engine/model", ""))
        self._engine_human_model.value = str(self.katrain.config("engine/humanlike_model", ""))
        self._engine_katago.value = str(self.katrain.config("engine/katago", ""))
        self._engine_config.value = str(self.katrain.config("engine/config", ""))
        self._engine_altcommand.value = str(self.katrain.config("engine/altcommand", ""))
        self._engine_max_visits.value = str(self.katrain.config("engine/max_visits", 0) or 0)
        self._engine_fast_visits.value = str(self.katrain.config("engine/fast_visits", 0) or 0)
        self._engine_max_time.value = str(self.katrain.config("engine/max_time", 0.0) or 0.0)
        self._engine_wide_root_noise.value = str(self.katrain.config("engine/wide_root_noise", 0.0) or 0.0)

        self._general_anim_pv_time.value = str(self.katrain.config("general/anim_pv_time", 0.5) or 0.0)
        self._general_debug_level.value = str(self.katrain.config("general/debug_level", OUTPUT_INFO) or 0)

        scroll = ScrollView(do_scroll_x=False)
        content = KtColumn(size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        engine = KtCard()
        engine.add_widget(self._row("engine:model", self._engine_model))
        engine.add_widget(self._row("engine:humanlike_model", self._engine_human_model))
        engine.add_widget(self._row("engine:katago", self._engine_katago))
        engine.add_widget(self._row("engine:config", self._engine_config))
        engine.add_widget(self._row("engine:altcommand", self._engine_altcommand))
        engine.add_widget(self._row("engine:max_visits", self._engine_max_visits))
        engine.add_widget(self._row("engine:fast_visits", self._engine_fast_visits))
        engine.add_widget(self._row("engine:max_time", self._engine_max_time))
        engine.add_widget(self._row("engine:wide_root_noise", self._engine_wide_root_noise))

        general = KtCard()
        general.add_widget(self._row("general:anim_pv_time", self._general_anim_pv_time))
        general.add_widget(self._row("general:debug_level", self._general_debug_level))
        general.add_widget(self._row("Sound", self._sound_enabled))
        general.add_widget(self._row("ui_state:restoresize", self._ui_restore_size))

        content.add_widget(engine)
        content.add_widget(general)
        scroll.add_widget(content)
        self.add_widget(scroll)

        self.add_widget(KtDivider())

        buttons = KtRow(padding=[0, 0, 0, 0], size_hint_y=None, height=dp(48))
        buttons.add_widget(KtButton(text="Cancel", on_click=self._dismiss))
        buttons.add_widget(KtButton(text="Apply", variant="primary", on_click=self.apply))
        self.add_widget(buttons)

    def _dismiss(self):
        if self.popup:
            self.popup.dismiss()

    def _row(self, label_key: str, field_widget):
        row = KtFormRow(label_key=label_key)
        row.set_field(field_widget)
        return row

    def apply(self):
        before_engine = dict(self.katrain._config.get("engine", {}))

        _set_config_path(self.katrain._config, "engine/model", self._engine_model.value.strip())
        _set_config_path(self.katrain._config, "engine/humanlike_model", self._engine_human_model.value.strip())
        _set_config_path(self.katrain._config, "engine/katago", self._engine_katago.value.strip())
        _set_config_path(self.katrain._config, "engine/config", self._engine_config.value.strip())
        _set_config_path(self.katrain._config, "engine/altcommand", self._engine_altcommand.value.strip())
        _set_config_path(self.katrain._config, "engine/max_visits", int(self._engine_max_visits.value or "0"))
        _set_config_path(self.katrain._config, "engine/fast_visits", int(self._engine_fast_visits.value or "0"))
        _set_config_path(self.katrain._config, "engine/max_time", float(self._engine_max_time.value or "0"))
        _set_config_path(self.katrain._config, "engine/wide_root_noise", float(self._engine_wide_root_noise.value or "0"))

        _set_config_path(self.katrain._config, "general/anim_pv_time", float(self._general_anim_pv_time.value or "0"))
        _set_config_path(self.katrain._config, "general/debug_level", int(self._general_debug_level.value or "0"))
        _set_config_path(self.katrain._config, "general/sound", bool(self._sound_enabled.active))
        _set_config_path(self.katrain._config, "ui_state/restoresize", bool(self._ui_restore_size.active))

        self.katrain.save_config()
        self.katrain.debug_level = self.katrain.config("general/debug_level", OUTPUT_INFO)

        after_engine = dict(self.katrain._config.get("engine", {}))
        if before_engine != after_engine:

            def restart_engine(_dt):
                self.katrain.controls.set_status("", STATUS_INFO)
                self.katrain.log("Restarting Engine after engine settings change")
                self.katrain.controls.set_status(i18n._("restarting engine"), STATUS_INFO)

                old_engine = self.katrain.engine
                old_proc = old_engine.katago_process
                if old_proc:
                    old_engine.shutdown(finish=False)
                new_engine = KataGoEngine(self.katrain, self.katrain.config("engine"))
                self.katrain.engine = new_engine
                self.katrain.game.engines = {"B": new_engine, "W": new_engine}
                self.katrain.game.analyze_all_nodes(analyze_fast=True)
                self.katrain.update_state()

            Clock.schedule_once(restart_engine, 0)

        self._dismiss()


class LoadSGFPopup(BaseConfigPopup):
    def __init__(self, katrain):
        super().__init__(katrain)
        app = App.get_running_app()
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
        app = App.get_running_app()
        self.filesel.favorites = [
            (os.path.abspath(app.gui.config("general/sgf_load")), "Last Load Dir"),
            (os.path.abspath(app.gui.config("general/sgf_save")), "Last Save Dir"),
        ]
        save_path = os.path.abspath(os.path.expanduser(App.get_running_app().gui.config("general/sgf_save") or "."))
        os.makedirs(save_path, exist_ok=True)

        def set_suggested(_widget, path):
            self.filesel.ids.file_text.text = os.path.join(path, self.suggested_filename)

        self.filesel.ids.list_view.bind(path=set_suggested)
        self.filesel.path = save_path
        self.filesel.select_string = "Save File"

    def on_submit(self):
        self.filesel.button_clicked()
