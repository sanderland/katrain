from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.properties import ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget

from katrain.gui.kivyutils import BackgroundMixin
from katrain.gui.theme import Theme


class KtDivider(Widget):
    """Thin horizontal line separator."""

    rgba = ListProperty([0, 0, 0, 0.10])

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
        self.spacing = kwargs.get("spacing", dp(Theme.SPACING_SM))
        self.padding = kwargs.get("padding", [dp(Theme.SPACING_SM)] * 4)


class KtColumn(BoxLayout):
    """Standard vertical column with KaTrain spacing/padding defaults."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = kwargs.get("spacing", dp(Theme.SPACING_SM))
        self.padding = kwargs.get("padding", [dp(Theme.SPACING_SM)] * 4)


class KtCard(BoxLayout, BackgroundMixin):
    """A background panel (card) used for sections and grouped controls."""

    background_color = ListProperty(Theme.BOX_BACKGROUND_COLOR)
    outline_color = ListProperty([0, 0, 0, 0])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = kwargs.get("orientation", "vertical")
        self.spacing = kwargs.get("spacing", dp(Theme.SPACING_SM))
        self.padding = kwargs.get("padding", [dp(Theme.SPACING_SM)] * 4)
        self.background_radius = kwargs.get("background_radius", dp(Theme.RADIUS_MD))

        auto_height = kwargs.get("auto_height", True)
        if auto_height and self.orientation == "vertical":
            self.size_hint_y = None
            self.bind(minimum_height=self.setter("height"))
