from __future__ import annotations

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ObjectProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from katrain.core.lang import i18n
from katrain.gui.kivyutils import KaTrainTextInput
from katrain.gui.theme import Theme


class FormValidationError(ValueError):
    pass


class KtFormRow(BoxLayout):
    """Label + field row with consistent sizing."""

    label_key = StringProperty("")
    helper_text = StringProperty("")
    error_text = StringProperty("")

    field = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.spacing = dp(Theme.SPACING_SM)
        self.size_hint_y = None
        self.height = dp(44)

        self._label = Label(
            text="",
            size_hint_x=0.45,
            color=Theme.TEXT_SECONDARY_COLOR,
            font_name=i18n.font_name,
            font_size=sp(Theme.FONT_SIZE_SM),
            halign="right",
            valign="middle",
        )
        # Wrap long labels and grow the row height instead of clipping.
        self._label.bind(width=lambda *_: setattr(self._label, "text_size", (self._label.width, None)))
        self._label.bind(texture_size=self._sync_height)

        # Anchor to keep small widgets (checkboxes) vertically centered.
        self._field_box = AnchorLayout(anchor_x="left", anchor_y="center", size_hint_x=0.55)

        self.add_widget(self._label)
        self.add_widget(self._field_box)

        self.bind(label_key=self._sync_label)
        self._sync_label()

    def _sync_height(self, *_args):
        label_h = self._label.texture_size[1] if self._label.texture_size else 0
        field_h = 0
        if self.field is not None:
            field_h = getattr(self.field, "height", 0) or 0
        # Keep default spacing and don't let single-line rows shrink.
        self.height = max(dp(44), label_h + dp(12), field_h + dp(8))

    def _sync_label(self, *_args):
        self._label.text = i18n._(self.label_key) if self.label_key else ""
        # Texture update happens on the next frame; resize after Kivy has updated it.
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
        self.font_size = kwargs.get("font_size", sp(Theme.INPUT_FONT_SIZE))
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
        self.padding = [dp(10), dp(6), dp(10), dp(6)]

        # Predictable sizing for forms.
        self.size_hint_y = None
        self.height = dp(40)
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


