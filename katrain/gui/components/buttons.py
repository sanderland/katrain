from kivy.core.image import Image as CoreImage
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, ObjectProperty, OptionProperty, StringProperty
from kivy.resources import resource_find
from kivy.uix.behaviors import ToggleButtonBehavior
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

    # Optional icon (mostly for toolbars).
    icon = StringProperty("")
    icon_only = BooleanProperty(False)
    icon_scale = NumericProperty(0.55)  # fraction of button height
    icon_color = ListProperty([1, 1, 1, 0.8])
    auto_icon_color = BooleanProperty(True)

    # Keep the built-in Button background fully transparent; we draw our own.
    background_color = ListProperty([0, 0, 0, 0])
    fill_color = ListProperty(Theme.LIGHTER_BACKGROUND_COLOR)
    color = ListProperty(Theme.BUTTON_TEXT_COLOR)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.font_name = kwargs.get("font_name", i18n.font_name)
        self.font_size = kwargs.get("font_size", sp(Theme.FONT_SIZE_MD))
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
        radius = (dp(Theme.RADIUS_SM), dp(Theme.RADIUS_SM))

        # Optional icon instructions (drawn above the background, behind text).
        self._icon_color_instr = None
        self._icon_rect_instr = None
        self._icon_texture = None
        with self.canvas.before:
            self._bg_color_instr = Color(rgba=self.fill_color)
            self._bg_rect_instr = RoundedRectangle(pos=self.pos, size=self.size, radius=[radius, radius, radius, radius])
            self._icon_color_instr = Color(rgba=self.icon_color)
            self._icon_rect_instr = Rectangle(pos=self.pos, size=(0, 0))
        self.bind(pos=self._sync_canvas, size=self._sync_canvas, fill_color=self._sync_canvas)
        self.bind(
            pos=self._sync_icon_canvas,
            size=self._sync_icon_canvas,
            icon=self._sync_icon_texture,
            icon_only=self._sync_icon_canvas,
            icon_scale=self._sync_icon_canvas,
            icon_color=self._sync_icon_canvas,
        )

        self.bind(on_release=self._handle_release)
        self.bind(variant=self._sync_variant, disabled=self._sync_variant, text_key=self._sync_text_key)
        self._sync_variant()
        self._sync_text_key()
        self._sync_icon_texture()

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
            if self.auto_icon_color:
                self.icon_color = [*self.color[:3], self.icon_color[3]]
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

        if self.auto_icon_color:
            self.icon_color = [*self.color[:3], self.icon_color[3]]

    def _handle_release(self, *_args):
        if self.on_click:
            self.on_click()

    def _sync_icon_texture(self, *_args):
        if not self._icon_rect_instr:
            return
        if not self.icon:
            self._icon_texture = None
            self._icon_rect_instr.texture = None
            self._icon_rect_instr.size = (0, 0)
            return

        source = resource_find(self.icon) or self.icon
        self._icon_texture = CoreImage(source).texture
        self._icon_rect_instr.texture = self._icon_texture
        self._sync_icon_canvas()

    def _sync_icon_canvas(self, *_args):
        if not self._icon_color_instr or not self._icon_rect_instr:
            return

        self._icon_color_instr.rgba = self.icon_color

        if not self._icon_texture:
            self._icon_rect_instr.size = (0, 0)
            return

        icon_px = min(self.width, self.height) * float(self.icon_scale)

        if self.icon_only or not (self.text or self.text_key):
            x = self.center_x - icon_px / 2
        else:
            x = self.x + dp(Theme.PADDING_MD)

        y = self.center_y - icon_px / 2
        self._icon_rect_instr.pos = (x, y)
        self._icon_rect_instr.size = (icon_px, icon_px)


class KtToggleButton(ToggleButtonBehavior, KtButton):
    """KtButton styling + toggle semantics (for segmented controls, tabs, etc.)."""

    inactive_fill_color = ListProperty(Theme.SURFACE_BG)
    inactive_text_color = ListProperty(Theme.BUTTON_INACTIVE_COLOR)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(state=self._sync_variant, inactive_fill_color=self._sync_variant, inactive_text_color=self._sync_variant)
        self._sync_variant()

    def _sync_variant(self, *_args):
        if self.disabled:
            # Match KtButton disabled colors.
            self.fill_color = Theme.BUTTON_INACTIVE_COLOR
            self.color = Theme.BACKGROUND_COLOR
            if self.auto_icon_color:
                self.icon_color = [*self.color[:3], self.icon_color[3]]
            return

        if self.state == "down":
            # Active state uses the normal KtButton variant styling.
            super()._sync_variant()
        else:
            self.fill_color = self.inactive_fill_color
            self.color = self.inactive_text_color
            if self.auto_icon_color:
                self.icon_color = [*self.color[:3], self.icon_color[3]]

