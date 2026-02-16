from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp, sp
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

    # Keep the built-in Button background fully transparent; we draw our own.
    background_color = ListProperty([0, 0, 0, 0])
    fill_color = ListProperty(Theme.LIGHTER_BACKGROUND_COLOR)
    color = ListProperty(Theme.BUTTON_TEXT_COLOR)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.font_name = kwargs.get("font_name", i18n.font_name)
        self.font_size = kwargs.get("font_size", sp(Theme.DESC_FONT_SIZE))
        # Kivy's default background image fights background_color.
        self.background_normal = ""
        self.background_down = ""
        self.background_disabled_normal = ""
        self.background_disabled_down = ""
        self.background_color = [0, 0, 0, 0]

        # Draw our own rounded background so primary/cancel are visually distinct.
        # (Kivy's default Button background is image-based and square.)
        self._bg_color_instr = None
        self._bg_rect_instr = None
        radius = (dp(6), dp(6))
        with self.canvas.before:
            self._bg_color_instr = Color(rgba=self.fill_color)
            self._bg_rect_instr = RoundedRectangle(pos=self.pos, size=self.size, radius=[radius, radius, radius, radius])
        self.bind(pos=self._sync_canvas, size=self._sync_canvas, fill_color=self._sync_canvas)

        self.bind(on_release=self._handle_release)
        self.bind(variant=self._sync_variant, disabled=self._sync_variant, text_key=self._sync_text_key)
        self._sync_variant()
        self._sync_text_key()

    def _sync_canvas(self, *_args):
        if self._bg_color_instr is not None:
            self._bg_color_instr.rgba = self.fill_color
        if self._bg_rect_instr is not None:
            self._bg_rect_instr.pos = self.pos
            self._bg_rect_instr.size = self.size

    def _sync_text_key(self, *_args):
        if self.text_key:
            self.text = i18n._(self.text_key)

    def _sync_variant(self, *_args):
        if self.disabled:
            self.fill_color = Theme.BUTTON_INACTIVE_COLOR
            self.color = Theme.BACKGROUND_COLOR
            return

        if self.variant == "primary":
            self.fill_color = Theme.PRIMARY_BUTTON_COLOR
            self.color = Theme.BUTTON_TEXT_COLOR
        elif self.variant == "danger":
            self.fill_color = Theme.MISTAKE_BUTTON_COLOR
            self.color = Theme.BUTTON_TEXT_COLOR
        else:
            self.fill_color = Theme.BOX_BACKGROUND_COLOR
            self.color = Theme.BUTTON_TEXT_COLOR

    def _handle_release(self, *_args):
        if self.on_click:
            self.on_click()

