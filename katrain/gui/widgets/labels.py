"""Labels: table cells for the game report, and a few clickable/scrollable variants."""

from kivy.properties import BooleanProperty, ListProperty, NumericProperty, OptionProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from katrain.core.lang import i18n
from katrain.gui.theme import Theme
from katrain.gui.widgets.base import BackgroundMixin, LeftButtonBehavior


class TableCellLabel(Label):
    """Cell of the game report table, which draws its own borders.

    `outlines` lists which of `left`/`right`/`top`/`bottom` to draw.
    """

    background_color = ListProperty([0, 0, 0, 0])
    line_width = NumericProperty(0)
    outlines = ListProperty([])
    outline_color = Theme.LINE_COLOR
    outline_width = NumericProperty(1.1)

    def __init__(self, **kwargs):
        kwargs["font_name"] = kwargs.get("font_name", i18n.font_name)
        super().__init__(**kwargs)


class TableStatLabel(TableCellLabel):
    """Table cell with a bar behind the text showing `value` as a fraction of `scale`."""

    side = StringProperty("right")
    value = NumericProperty(0)
    scale = NumericProperty(100)
    bar_color = ListProperty([0, 0, 0, 1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "outlines" not in kwargs:
            self.outlines = ["left"] if self.side == "right" else ["right"]


class TableHeaderLabel(TableCellLabel):
    outlines = ["bottom"]


class StatsLabel(BoxLayout):
    """One `label: value` row of the move statistics box."""

    text = StringProperty("")
    label = StringProperty("")
    color = ListProperty([1, 1, 1, 1])
    hidden = BooleanProperty(False)
    font_name = StringProperty(Theme.DEFAULT_FONT)


class CircleWithText(Widget):
    """Black or white stone image with a number on it, used for captures and player colour."""

    text = StringProperty("0")
    player = OptionProperty("B", options=["B", "W"])
    min_size = NumericProperty(50)


class ClickableLabel(LeftButtonBehavior, Label):
    pass


class ClickableCircle(LeftButtonBehavior, CircleWithText):
    pass


class ScrollableLabel(ScrollView, BackgroundMixin):
    __events__ = ["on_ref_press"]
    outline_color = ListProperty([0, 0, 0, 0])  # mixin not working for some reason
    text = StringProperty("")
    line_height = NumericProperty(1)
    markup = BooleanProperty(False)

    def on_ref_press(self, ref):
        pass
