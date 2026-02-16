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
        super().__init__(**kwargs)
        self.orientation = kwargs.get("orientation", "vertical")
        self.spacing = kwargs.get("spacing", dp(Theme.CP_SPACING))
        self.padding = kwargs.get("padding", [dp(Theme.CP_PADDING)] * 4)
        self.background_radius = kwargs.get("background_radius", dp(6))

        # Most cards should naturally size to content when used inside a ScrollView.
        auto_height = kwargs.get("auto_height", True)
        if auto_height and self.orientation == "vertical":
            self.size_hint_y = None
            self.bind(minimum_height=self.setter("height"))
