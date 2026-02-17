from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ObjectProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from katrain.core.lang import i18n
from katrain.gui.kivyutils import KaTrainTextInput, KeyValueSpinner
from katrain.gui.theme import Theme


class FormValidationError(ValueError):
    pass


def _parse_path(path: str) -> list[str | int]:
    parts: list[str | int] = []
    for raw in path.split("/"):
        if "::" in raw:
            key, index = raw.split("::", 1)
            if key:
                parts.append(key)
            parts.append(int(index))
            continue

        # Allow list indexing via numeric segments too (e.g. `foo/0/bar`).
        if raw.isdigit():
            parts.append(int(raw))
        else:
            parts.append(raw)
    return parts


def _get_nested(config: dict[str, Any], path: str) -> Any:
    cur: Any = config
    for part in _parse_path(path):
        cur = cur[part]
    return cur


def _set_nested(config: dict[str, Any], path: str, value: Any) -> None:
    keys = _parse_path(path)
    cur: Any = config
    for key, next_key in zip(keys[:-1], keys[1:]):
        if isinstance(key, int):
            while len(cur) <= key:
                cur.append(None)
            nxt = cur[key]
            if nxt is None:
                nxt = {} if isinstance(next_key, str) else []
                cur[key] = nxt
            cur = nxt
            continue

        nxt = cur.get(key)
        if nxt is None:
            nxt = {} if isinstance(next_key, str) else []
            cur[key] = nxt
        cur = nxt

    last = keys[-1]
    if isinstance(last, int):
        while len(cur) <= last:
            cur.append(None)
        cur[last] = value
    else:
        cur[last] = value


@dataclass
class FieldSpec:
    key: str
    label_key: str
    default: Any = None
    parser: Callable[[Any], Any] | None = None
    validator: Callable[[Any], str | None] | None = None
    required: bool = False

    # Presentation metadata (used by settings/search UIs).
    section: str = ""
    helper_key: str = ""
    search_terms: list[str] = field(default_factory=list)

    def parse(self, raw: Any) -> Any:
        if self.parser is None:
            return raw
        try:
            return self.parser(raw)
        except (ValueError, TypeError) as exc:
            raise FormValidationError(str(exc)) from exc

    def validate(self, value: Any) -> str | None:
        if self.required:
            if value is None:
                return "Required."
            if isinstance(value, str) and not value.strip():
                return "Required."

        if self.validator is None:
            return None

        try:
            return self.validator(value)
        except (ValueError, TypeError, FormValidationError) as exc:
            return str(exc)


class FormModel:
    """Explicit form model keyed by config paths like `engine/model`."""

    def __init__(self):
        self._specs: dict[str, FieldSpec] = {}
        self._values: dict[str, Any] = {}
        self._errors: dict[str, str] = {}

    def add(self, spec: FieldSpec) -> None:
        if spec.key in self._specs:
            raise KeyError(f"Duplicate field key: {spec.key}")
        self._specs[spec.key] = spec
        self._values[spec.key] = spec.default

    def set(self, key: str, value: Any) -> None:
        spec = self._specs[key]
        try:
            self._values[key] = spec.parse(value)
        except FormValidationError as exc:
            self._errors[key] = str(exc)
            raise
        else:
            self._errors.pop(key, None)

    def get(self, key: str) -> Any:
        return self._values[key]

    def spec(self, key: str) -> FieldSpec:
        return self._specs[key]

    def errors(self) -> dict[str, str]:
        return dict(self._errors)

    def validate(self) -> dict[str, str]:
        errors: dict[str, str] = {}
        for key, spec in self._specs.items():
            msg = spec.validate(self._values[key])
            if msg:
                errors[key] = msg
        self._errors = errors
        return errors

    def specs_by_section(self) -> dict[str, list[FieldSpec]]:
        sections: dict[str, list[FieldSpec]] = {}
        for spec in self._specs.values():
            sections.setdefault(spec.section or "", []).append(spec)
        return sections

    def load_from_config(self, config: dict[str, Any]) -> None:
        for key, spec in self._specs.items():
            try:
                self._values[key] = _get_nested(config, key)
            except KeyError:
                self._values[key] = spec.default

    def apply_to_config(self, config: dict[str, Any]) -> None:
        for key in self._specs:
            _set_nested(config, key, self._values[key])

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)


class KtFormRow(BoxLayout):
    """Label + field row with consistent sizing."""

    label_key = StringProperty("")
    helper_text = StringProperty("")
    error_text = StringProperty("")

    field = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = dp(Theme.SPACING_XS)
        self.size_hint_y = None
        self.height = dp(Theme.FORM_ROW_HEIGHT)

        self._top_row = BoxLayout(orientation="horizontal", spacing=dp(Theme.SPACING_SM), size_hint_y=None)
        self._label = Label(
            text="",
            size_hint_x=0.45,
            color=Theme.TEXT_COLOR,
            font_name=i18n.font_name,
            font_size=sp(Theme.FONT_SIZE_MD),
            halign="right",
            valign="middle",
        )
        # Wrap long labels and grow the row height instead of clipping.
        self._label.bind(width=lambda *_: setattr(self._label, "text_size", (self._label.width, None)))
        self._label.bind(texture_size=self._sync_height)

        # Anchor to keep small widgets (checkboxes) vertically centered.
        self._field_box = AnchorLayout(anchor_x="left", anchor_y="center", size_hint_x=0.55)

        self._top_row.add_widget(self._label)
        self._top_row.add_widget(self._field_box)

        self._helper = Label(
            text="",
            size_hint_y=None,
            height=0,
            color=Theme.MENU_ITEM_SHORTCUT_COLOR,
            font_name=i18n.font_name,
            font_size=sp(Theme.FONT_SIZE_SM),
            halign="left",
            valign="middle",
        )
        self._helper.bind(width=lambda *_: setattr(self._helper, "text_size", (self._helper.width, None)))
        self._helper.bind(texture_size=self._sync_height)

        self.add_widget(self._top_row)
        self.add_widget(self._helper)

        self.bind(label_key=self._sync_label, helper_text=self._sync_helper, error_text=self._sync_helper)
        self._sync_label()
        self._sync_helper()

    def _sync_height(self, *_args):
        label_h = self._label.texture_size[1] if self._label.texture_size else 0
        field_h = 0
        if self.field is not None:
            field_h = getattr(self.field, "height", 0) or 0
        # Keep default spacing and don't let single-line rows shrink.
        top_h = max(dp(Theme.FORM_ROW_HEIGHT), label_h + dp(16), field_h + dp(12))
        self._top_row.height = top_h

        helper_h = 0
        if self._helper.text:
            helper_h = max(self._helper.texture_size[1] if self._helper.texture_size else 0, dp(18))
        self._helper.height = helper_h
        self._helper.opacity = 1 if helper_h else 0

        self.height = top_h + helper_h + (self.spacing if helper_h else 0)

    def _sync_label(self, *_args):
        self._label.text = i18n._(self.label_key) if self.label_key else ""
        # Texture update happens on the next frame; resize after Kivy has updated it.
        Clock.schedule_once(self._sync_height, 0)

    def _sync_helper(self, *_args):
        if self.error_text:
            self._helper.text = self.error_text
            self._helper.color = Theme.ERROR_BORDER_COLOR
        elif self.helper_text:
            self._helper.text = i18n._(self.helper_text) if self.helper_text else ""
            self._helper.color = Theme.MENU_ITEM_SHORTCUT_COLOR
        else:
            self._helper.text = ""
        Clock.schedule_once(self._sync_height, 0)

    def set_field(self, widget) -> None:
        self._field_box.clear_widgets()
        self.field = widget
        self._field_box.add_widget(widget)
        # Recompute row height when the field is swapped.
        self._sync_height()


class KtTextField(KaTrainTextInput):
    """Text field with `value` as the canonical API."""

    value = StringProperty("")
    required = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.font_name = kwargs.get("font_name", i18n.font_name)
        self.font_size = kwargs.get("font_size", sp(Theme.FONT_SIZE_LG))
        self.multiline = kwargs.get("multiline", False)
        self.write_tab = False

        # Dark-theme styling (the old KV did this implicitly).
        self.background_normal = ""
        self.background_active = ""
        self.background_color = Theme.LIGHTER_BACKGROUND_COLOR
        self.foreground_color = Theme.INPUT_FONT_COLOR
        self.cursor_color = Theme.TEXT_COLOR
        self.selection_color = [Theme.CHECKBOX_COLOR[0], Theme.CHECKBOX_COLOR[1], Theme.CHECKBOX_COLOR[2], 0.35]
        # The previous padding caused vertical text clipping at 20sp/40dp on macOS.
        self.padding = [dp(Theme.INPUT_PADDING_X), dp(Theme.INPUT_PADDING_Y), dp(Theme.INPUT_PADDING_X), dp(Theme.INPUT_PADDING_Y)]

        # Predictable sizing for forms.
        self.size_hint_y = None
        self.height = dp(Theme.INPUT_HEIGHT)
        self.size_hint_x = 1

        self.bind(text=self._sync_value_from_text, value=self._sync_text_from_value)
        self._sync_text_from_value()

    def _sync_value_from_text(self, *_args):
        self.value = self.text

    def _sync_text_from_value(self, *_args):
        if self.text != self.value:
            self.text = self.value


class KtNumberField(KtTextField):
    number_type = StringProperty("int")  # 'int' or 'float'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._sync_input_filter()

    def on_number_type(self, *_args):
        self._sync_input_filter()

    def _sync_input_filter(self):
        self.input_filter = "int" if self.number_type == "int" else "float"

    def parsed_value(self) -> int | float:
        if self.number_type == "int":
            return int(self.value or "0")
        return float(self.value or "0.0")


class KtSelectField(KeyValueSpinner):
    """Select field using KeyValueSpinner; exposes `value_key`."""

    value_key = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.font_size = kwargs.get("font_size", sp(Theme.FONT_SIZE_LG))
        self.font_name = kwargs.get("font_name", i18n.font_name)
        self.bind(selected_index=self._sync_value_key)
        self._sync_value_key()

    def _sync_value_key(self, *_args):
        self.value_key = self.selected[1]

