from kivy.metrics import sp
from kivy.properties import ListProperty, ObjectProperty, OptionProperty, StringProperty
from kivy.uix.button import Button

from katrain.core.lang import i18n
from katrain.gui.theme import Theme


class KtButton(Button):
    """Canonical KaTrain button.

    Styling is intentionally simple and Python-driven to reduce KV sprawl.
    """

    variant = OptionProperty("default", options=["default", "primary", "danger"])
    text_key = StringProperty("")  # optional i18n key; overrides `text` if set
    on_click = ObjectProperty(None, allownone=True)

    background_color = ListProperty(Theme.LIGHTER_BACKGROUND_COLOR)
    color = ListProperty(Theme.BUTTON_TEXT_COLOR)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.font_name = kwargs.get("font_name", i18n.font_name)
        self.font_size = kwargs.get("font_size", sp(Theme.DESC_FONT_SIZE))
        # Kivy's default background image fights background_color.
        self.background_normal = ""
        self.background_down = ""
        self.bind(on_release=self._handle_release)
        self.bind(variant=self._sync_variant, disabled=self._sync_variant, text_key=self._sync_text_key)
        self._sync_variant()
        self._sync_text_key()

    def _sync_text_key(self, *_args):
        if self.text_key:
            self.text = i18n._(self.text_key)

    def _sync_variant(self, *_args):
        if self.disabled:
            self.background_color = Theme.BUTTON_INACTIVE_COLOR
            self.color = Theme.BACKGROUND_COLOR
            return

        if self.variant == "primary":
            self.background_color = Theme.LIGHTER_BACKGROUND_COLOR
            self.color = Theme.BUTTON_TEXT_COLOR
        elif self.variant == "danger":
            self.background_color = Theme.MISTAKE_BUTTON_COLOR
            self.color = Theme.BUTTON_TEXT_COLOR
        else:
            self.background_color = Theme.BOX_BACKGROUND_COLOR
            self.color = Theme.BUTTON_TEXT_COLOR

    def _handle_release(self, *_args):
        if self.on_click:
            self.on_click()

