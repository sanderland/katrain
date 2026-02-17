from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    ObjectProperty,
    OptionProperty,
    StringProperty,
)
from kivy.uix.behaviors import ButtonBehavior, ToggleButtonBehavior
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.widget import Widget

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
        self.background_normal = ""
        self.background_down = ""
        self.background_disabled_normal = ""
        self.background_disabled_down = ""
        self.background_color = [0, 0, 0, 0]

        self._bg_color_instr = None
        self._bg_rect_instr = None
        radius = dp(Theme.RADIUS_MD)
        with self.canvas.before:
            self._bg_color_instr = Color(rgba=self.fill_color)
            self._bg_rect_instr = RoundedRectangle(
                pos=self.pos, size=self.size, radius=[radius, radius, radius, radius]
            )
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
            self.color = [1, 1, 1, 0.6]
            return

        if self.variant == "primary":
            self.fill_color = Theme.PRIMARY_BUTTON_COLOR
            self.color = [1, 1, 1, 1]
        elif self.variant == "danger":
            self.fill_color = Theme.MISTAKE_BUTTON_COLOR
            self.color = [1, 1, 1, 1]
        else:
            self.fill_color = Theme.LIGHTER_BACKGROUND_COLOR
            self.color = Theme.TEXT_COLOR

    def _handle_release(self, *_args):
        if self.on_click:
            self.on_click()


class KtIconButton(ButtonBehavior, Widget):
    """Round icon button with subtle background on press/hover."""

    icon = StringProperty("")
    icon_color = ListProperty([1, 1, 1, 1])
    bg_color = ListProperty([0, 0, 0, 0])
    icon_size_ratio = NumericProperty(0.55)
    disabled = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._bg_color_instr = None
        self._bg_ellipse = None
        self._image = Image(mipmap=True)
        self._image.color = self.icon_color

        with self.canvas.before:
            self._bg_color_instr = Color(rgba=self.bg_color)
            self._bg_ellipse = Ellipse(pos=self.pos, size=self.size)

        self.add_widget(self._image)
        self.bind(
            pos=self._sync,
            size=self._sync,
            icon=self._sync_icon,
            icon_color=self._sync_color,
            disabled=self._sync_color,
            bg_color=self._sync_bg,
        )
        self._sync_icon()
        self._sync()

    def _sync(self, *_args):
        s = min(self.width, self.height)
        self._bg_ellipse.pos = (self.center_x - s / 2, self.center_y - s / 2)
        self._bg_ellipse.size = (s, s)
        icon_s = s * self.icon_size_ratio
        self._image.size = (icon_s, icon_s)
        self._image.pos = (self.center_x - icon_s / 2, self.center_y - icon_s / 2)

    def _sync_icon(self, *_args):
        self._image.source = self.icon

    def _sync_color(self, *_args):
        if self.disabled:
            self._image.color = [1, 1, 1, 0.3]
        else:
            self._image.color = self.icon_color

    def _sync_bg(self, *_args):
        if self._bg_color_instr:
            self._bg_color_instr.rgba = self.bg_color

    def on_press(self):
        if not self.disabled:
            self.bg_color = [1, 1, 1, 0.08]

    def on_release(self):
        self.bg_color = [0, 0, 0, 0]


class KtToggleButton(ToggleButtonBehavior, Widget):
    """Clean toggle button for toolbar use -- icon + optional text label."""

    icon = StringProperty("")
    text = StringProperty("")
    active_color = ListProperty(Theme.PLAY_ANALYZE_TAB_COLOR)
    inactive_color = ListProperty(Theme.TEXT_SECONDARY_COLOR)
    font_name = StringProperty(Theme.DEFAULT_FONT)
    disabled = BooleanProperty(False)
    tri_state = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._bg_color_instr = None
        self._bg_rect = None
        self._image = None
        self._label = None

        with self.canvas.before:
            self._bg_color_instr = Color(rgba=[0, 0, 0, 0])
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(Theme.RADIUS_SM)] * 4)

        if self.icon:
            self._image = Image(source=self.icon, mipmap=True)
            self.add_widget(self._image)

        self.bind(
            pos=self._sync,
            size=self._sync,
            state=self._sync_visual,
            disabled=self._sync_visual,
            icon=self._sync_icon,
        )
        self._sync_visual()

    @property
    def active(self):
        return self.state == "down"

    def _sync(self, *_args):
        if self._bg_rect:
            self._bg_rect.pos = self.pos
            self._bg_rect.size = self.size
        if self._image:
            s = min(self.width, self.height) * 0.5
            self._image.size = (s, s)
            self._image.pos = (self.center_x - s / 2, self.center_y - s / 2)

    def _sync_icon(self, *_args):
        if self._image:
            self._image.source = self.icon

    def _sync_visual(self, *_args):
        is_active = self.state == "down"
        if self.disabled:
            col = [0.4, 0.4, 0.4, 0.5]
            bg = [0, 0, 0, 0]
        elif is_active:
            col = self.active_color
            bg = [self.active_color[0], self.active_color[1], self.active_color[2], 0.12]
        else:
            col = self.inactive_color
            bg = [0, 0, 0, 0]

        if self._image:
            self._image.color = col
        if self._bg_color_instr:
            self._bg_color_instr.rgba = bg
