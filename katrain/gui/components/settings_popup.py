from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from kivy.metrics import dp, sp
from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from katrain.core.lang import i18n
from katrain.gui.components.buttons import KtButton
from katrain.gui.components.forms import FieldSpec, FormModel, FormValidationError, KtFormRow, KtNumberField, KtSelectField, KtTextField
from katrain.gui.components.layout import KtCard, KtColumn, KtDivider, KtRow
from katrain.gui.components.popup import KtPopupContent
from katrain.gui.kivyutils import KeyValueSpinner
from katrain.gui.theme import Theme


@dataclass(frozen=True)
class _BoundField:
    spec: FieldSpec
    row: KtFormRow | None
    widget: Any
    read_widget: Callable[[], Any]
    write_widget: Callable[[Any], None]

    def search_blob(self) -> str:
        bits: list[str] = [
            self.spec.key,
            self.spec.label_key,
            i18n._(self.spec.label_key) if self.spec.label_key else "",
            self.spec.section,
        ]
        if self.spec.helper_key:
            bits.append(self.spec.helper_key)
            bits.append(i18n._(self.spec.helper_key))
        bits.extend(self.spec.search_terms)
        return " ".join(b for b in bits if b).lower()


class KtSettingsPopup(KtPopupContent):
    """Standard settings popup scaffold (scroll, sections, apply/cancel, optional search)."""

    katrain = ObjectProperty(None, allownone=True)
    search_query = StringProperty("")

    apply_text = StringProperty("Apply")
    cancel_text = StringProperty("Cancel")

    def __init__(self, *, katrain, form: FormModel | None = None, enable_search: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.katrain = katrain
        self.form = form or FormModel()

        self._enable_search = enable_search
        self._bindings: dict[str, _BoundField] = {}
        self._sections: dict[str, KtCard] = {}
        self._section_bodies: dict[str, BoxLayout] = {}

        self.orientation = "vertical"
        self.spacing = dp(Theme.SPACING_SM)
        self.padding = [dp(Theme.PADDING_SM)] * 4

        self._header = KtRow(padding=[0, 0, 0, 0], size_hint_y=None, height=dp(Theme.INPUT_HEIGHT))
        if enable_search:
            self._search = KtTextField(multiline=False)
            self._search.hint_text = "Search"
            self._search.bind(text=self._on_search_text)
            self._header.add_widget(self._search)
        self.add_widget(self._header if enable_search else Label(size_hint_y=None, height=0))

        self._scroll = ScrollView(do_scroll_x=False)
        self._content = KtColumn(size_hint_y=None, padding=[0, 0, 0, 0])
        self._content.bind(minimum_height=self._content.setter("height"))
        self._scroll.add_widget(self._content)
        self.add_widget(self._scroll)

        self.add_widget(KtDivider())

        self._buttons = KtRow(padding=[0, 0, 0, 0], size_hint_y=None, height=dp(Theme.BUTTON_HEIGHT))
        self._buttons.add_widget(KtButton(text=self.cancel_text, on_click=self._dismiss))
        self._apply_btn = KtButton(text=self.apply_text, variant="primary", on_click=self._apply_clicked)
        self._buttons.add_widget(self._apply_btn)
        self.add_widget(self._buttons)

    # ---- section + row helpers ----

    def add_section(self, title: str) -> BoxLayout:
        if title in self._section_bodies:
            return self._section_bodies[title]

        card = KtCard(auto_height=True)
        if title:
            hdr = Label(
                text=title,
                size_hint_y=None,
                height=dp(24),
                color=Theme.TEXT_COLOR,
                font_name=i18n.font_name,
                font_size=sp(Theme.FONT_SIZE_MD),
                halign="left",
                valign="middle",
            )
            hdr.bind(width=lambda *_: setattr(hdr, "text_size", (hdr.width, None)))
            card.add_widget(hdr)

        body = KtColumn(size_hint_y=None, padding=[0, 0, 0, 0], spacing=dp(Theme.SPACING_XS))
        body.bind(minimum_height=body.setter("height"))
        card.add_widget(body)

        self._sections[title] = card
        self._section_bodies[title] = body
        self._content.add_widget(card)
        return body

    def add_field(self, spec: FieldSpec, widget) -> None:
        row = KtFormRow(label_key=spec.label_key)
        if spec.helper_key:
            row.helper_text = spec.helper_key
        row.set_field(widget)

        section_body = self.add_section(spec.section)
        self.bind_field(spec, widget, row=row)
        section_body.add_widget(row)

    def bind_field(self, spec: FieldSpec, widget, *, row: KtFormRow | None = None) -> None:
        """Register a field binding with the form model.

        Used for both normal `KtFormRow` rows and grid/table layouts (row=None).
        """

        self.form.add(spec)
        self._bindings[spec.key] = _BoundField(
            spec=spec,
            row=row,
            widget=widget,
            read_widget=lambda w=widget: self._read_widget_value(w),
            write_widget=lambda v, w=widget: self._write_widget_value(w, v),
        )

    def load_from_config(self, config: dict[str, Any]) -> None:
        self.form.load_from_config(config)
        for key, binding in self._bindings.items():
            binding.write_widget(self.form.get(key))

    # ---- apply/validate ----

    def _apply_clicked(self):
        errors = self._collect_and_validate()
        if errors:
            return
        self.on_apply(self.form.as_dict())

    def on_apply(self, values: dict[str, Any]) -> None:
        """Override in subclasses. Default writes values into KaTrain's config and saves."""
        self.form.apply_to_config(self.katrain._config)
        self.katrain.save_config()
        self._dismiss()

    def _collect_and_validate(self) -> dict[str, str]:
        # Parse + store raw field values into the model.
        for key, binding in self._bindings.items():
            try:
                self.form.set(key, binding.read_widget())
            except FormValidationError:
                pass

        errors = self.form.validate()
        errors = {**errors, **self.form.errors()}

        # Render errors onto rows.
        for key, binding in self._bindings.items():
            if binding.row is not None:
                binding.row.error_text = errors.get(key, "")
        return errors

    def _dismiss(self):
        if self.popup:
            self.popup.dismiss()

    # ---- widget adapters ----

    def _read_widget_value(self, widget) -> Any:
        if isinstance(widget, KtNumberField):
            return widget.value
        if isinstance(widget, KtTextField):
            return widget.value
        if isinstance(widget, KtSelectField):
            return widget.value_key
        if isinstance(widget, KeyValueSpinner):
            return widget.selected[1]
        if hasattr(widget, "active"):
            return bool(widget.active)
        if hasattr(widget, "text"):
            return widget.text
        raise TypeError(f"Unsupported field widget: {type(widget)}")

    def _write_widget_value(self, widget, value: Any) -> None:
        if isinstance(widget, KtNumberField):
            widget.value = str(value if value is not None else "")
            return
        if isinstance(widget, KtTextField):
            widget.value = str(value if value is not None else "")
            return
        if isinstance(widget, KtSelectField):
            widget.select_key(value)
            return
        if isinstance(widget, KeyValueSpinner):
            widget.select_key(value)
            return
        if hasattr(widget, "active"):
            widget.active = bool(value)
            return
        if hasattr(widget, "text"):
            widget.text = str(value if value is not None else "")
            return
        raise TypeError(f"Unsupported field widget: {type(widget)}")

    # ---- search ----

    def _on_search_text(self, _field, text: str):
        self.search_query = (text or "").strip().lower()
        self._apply_search_filter()

    def _apply_search_filter(self) -> None:
        if not self._enable_search:
            return

        q = self.search_query
        if not q:
            for binding in self._bindings.values():
                if binding.row is not None:
                    self._set_widget_visible(binding.row, True)
            return

        for key, binding in self._bindings.items():
            show = q in binding.search_blob()
            if binding.row is not None:
                self._set_widget_visible(binding.row, show)

    def _set_widget_visible(self, widget, visible: bool) -> None:
        widget.opacity = 1 if visible else 0
        widget.disabled = not visible
        if visible:
            # Restore computed height.
            if hasattr(widget, "_sync_height"):
                widget._sync_height()
        else:
            widget.height = 0
