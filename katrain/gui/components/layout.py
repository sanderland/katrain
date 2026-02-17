from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from katrain.gui.kivyutils import BackgroundMixin
from katrain.gui.theme import Theme


class KtSpacer(Widget):
    """A simple spacer with predictable default sizing."""

    min_width = NumericProperty(0)
    min_height = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = kwargs.get("size_hint", (None, None))
        self.width = kwargs.get("width", self.min_width)
        self.height = kwargs.get("height", self.min_height)


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


class KtToolbar(BoxLayout, BackgroundMixin):
    """Horizontal toolbar with consistent height and background."""

    background_color = ListProperty(Theme.BACKGROUND_COLOR)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = kwargs.get("height", dp(44))
        self.spacing = kwargs.get("spacing", dp(Theme.SPACING_SM))
        self.padding = kwargs.get("padding", [dp(Theme.SPACING_MD), dp(Theme.SPACING_XS)] * 2)


class _KtTabButton(ButtonBehavior, BoxLayout, BackgroundMixin):
    """Individual tab in a KtTabBar."""

    text = StringProperty("")
    active = BooleanProperty(False)
    tab_color = ListProperty(Theme.TEXT_COLOR)
    font_name = StringProperty(Theme.DEFAULT_FONT)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.padding = [dp(Theme.SPACING_SM), 0]

        self._label = Label(
            text=self.text,
            font_name=self.font_name,
            font_size=dp(Theme.FONT_SIZE_SM),
            color=self.tab_color,
            halign="center",
            valign="middle",
        )
        self._label.bind(size=lambda *_: setattr(self._label, "text_size", self._label.size))
        self.add_widget(self._label)

        self._indicator_color = None
        self._indicator_rect = None
        with self.canvas.after:
            self._indicator_color = Color(rgba=[0, 0, 0, 0])
            self._indicator_rect = Rectangle(pos=self.pos, size=(self.width, dp(2)))

        self.bind(
            pos=self._sync,
            size=self._sync,
            text=self._sync_label,
            active=self._sync_visual,
            tab_color=self._sync_visual,
        )
        self._sync_visual()

    def _sync(self, *_args):
        if self._indicator_rect:
            self._indicator_rect.pos = (self.x, self.y)
            self._indicator_rect.size = (self.width, dp(2))
        if self._label:
            self._label.text_size = self._label.size

    def _sync_label(self, *_args):
        self._label.text = self.text

    def _sync_visual(self, *_args):
        if self.active:
            self._label.color = self.tab_color
            self._label.bold = True
            if self._indicator_color:
                self._indicator_color.rgba = self.tab_color
        else:
            self._label.color = Theme.TEXT_TERTIARY_COLOR
            self._label.bold = False
            if self._indicator_color:
                self._indicator_color.rgba = [0, 0, 0, 0]


class KtTabBar(BoxLayout):
    """Horizontal tab bar. Dispatches ``on_tab_select(index, key)``."""

    __events__ = ["on_tab_select"]

    def __init__(self, tabs: list[tuple[str, str]] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = kwargs.get("height", dp(32))
        self.spacing = dp(2)
        self._tabs: list[_KtTabButton] = []
        self._tab_keys: list[str] = []
        if tabs:
            for key, label in tabs:
                self.add_tab(key, label)

    def add_tab(self, key: str, label: str, color: list | None = None, active: bool = False):
        btn = _KtTabButton(text=label, tab_color=color or Theme.TEXT_COLOR, active=active)
        btn.bind(on_release=lambda *_a, k=key: self._on_click(k))
        self._tabs.append(btn)
        self._tab_keys.append(key)
        self.add_widget(btn)
        # Add a flex spacer after to push tabs left
        return btn

    def _on_click(self, key: str):
        idx = self._tab_keys.index(key)
        self.select(idx)
        self.dispatch("on_tab_select", idx, key)

    def select(self, index: int):
        for i, tab in enumerate(self._tabs):
            tab.active = i == index

    def on_tab_select(self, index, key):
        pass
