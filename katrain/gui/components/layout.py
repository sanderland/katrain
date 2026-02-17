from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.properties import ListProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget

from katrain.gui.kivyutils import BackgroundMixin
from katrain.gui.theme import Theme


class KtSpacer(Widget):
    """A simple spacer with predictable default sizing."""

    min_width = NumericProperty(0)
    min_height = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Keep it easy to drop into BoxLayouts.
        self.size_hint = kwargs.get("size_hint", (None, None))
        self.width = kwargs.get("width", self.min_width)
        self.height = kwargs.get("height", self.min_height)


class KtDivider(Widget):
    """Thin horizontal line separator."""

    rgba = ListProperty([*Theme.MENU_ITEM_SHORTCUT_COLOR[:3], 0.35])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_x = 1
        self.size_hint_y = None
        self.height = kwargs.get("height", dp(1))

        with self.canvas:
            self._color = Color(rgba=self.rgba)
            self._rect = Rectangle(pos=self.pos, size=self.size)

        self.bind(pos=self._sync_canvas, size=self._sync_canvas, rgba=self._sync_canvas)

    def _sync_canvas(self, *_args):
        self._color.rgba = self.rgba
        self._rect.pos = self.pos
        self._rect.size = self.size


class KtRow(BoxLayout):
    """Standard horizontal row with KaTrain spacing/padding defaults."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.spacing = kwargs.get("spacing", dp(Theme.CP_SPACING))
        self.padding = kwargs.get("padding", [dp(Theme.CP_PADDING)] * 4)


class KtColumn(BoxLayout):
    """Standard vertical column with KaTrain spacing/padding defaults."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = kwargs.get("spacing", dp(Theme.CP_SPACING))
        self.padding = kwargs.get("padding", [dp(Theme.CP_PADDING)] * 4)


class KtCard(BoxLayout, BackgroundMixin):
    """A background panel (card) used for sections and grouped controls."""

    background_color = ListProperty(Theme.BOX_BACKGROUND_COLOR)
    outline_color = ListProperty([0, 0, 0, 0])

    def __init__(self, **kwargs):
        # `auto_height` is a convenience flag, not a Kivy Property.
        auto_height = kwargs.pop("auto_height", True)
        super().__init__(**kwargs)
        self.orientation = kwargs.get("orientation", "vertical")
        self.spacing = kwargs.get("spacing", dp(Theme.CP_SPACING))
        self.padding = kwargs.get("padding", [dp(Theme.CP_PADDING)] * 4)
        self.background_radius = kwargs.get("background_radius", dp(6))

        # Most cards should naturally size to content when used inside a ScrollView.
        if auto_height and self.orientation == "vertical":
            self.size_hint_y = None
            self.bind(minimum_height=self.setter("height"))


class KtToolbar(BoxLayout, BackgroundMixin):
    """A simple full-width top bar container."""

    background_color = ListProperty(Theme.SURFACE_BG)
    outline_color = ListProperty([0, 0, 0, 0])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = kwargs.get("height", dp(Theme.TOOLBAR_HEIGHT))
        self.spacing = kwargs.get("spacing", dp(Theme.SPACING_SM))
        self.padding = kwargs.get(
            "padding",
            [dp(Theme.PADDING_MD), dp(Theme.PADDING_SM), dp(Theme.PADDING_MD), dp(Theme.PADDING_SM)],
        )
        self.background_radius = kwargs.get("background_radius", 0)
        self.outline_width = kwargs.get("outline_width", 0)
