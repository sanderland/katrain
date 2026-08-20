"""Widgets used by KaTrain's `.kv` files.

Importing this package pulls in every widget module, which is what registers the
classes with Kivy's `Factory` so the `.kv` files can refer to them by name.
"""

from katrain.gui.widgets.base import BackgroundLabel, BackgroundMixin, BGBoxLayout, LeftButtonBehavior
from katrain.gui.widgets.buttons import (
    AutoSizedButton,
    AutoSizedRectangleButton,
    AutoSizedRectangleToggleButton,
    PauseButton,
    SizedButton,
    SizedRectangleButton,
    SizedRectangleToggleButton,
    SizedToggleButton,
    ToggleButtonMixin,
    TransparentIconButton,
)
from katrain.gui.widgets.drawing import cached_text_texture, cached_texture, draw_circle, draw_text
from katrain.gui.widgets.filebrowser import I18NFileBrowser
from katrain.gui.widgets.graph import ScoreGraph
from katrain.gui.widgets.inputs import I18NSpinner, KeyValueSpinner
from katrain.gui.widgets.labels import (
    CircleWithText,
    ClickableCircle,
    ClickableLabel,
    ScrollableLabel,
    StatsLabel,
    TableCellLabel,
    TableHeaderLabel,
    TableStatLabel,
)
from katrain.gui.widgets.material import (
    CircularRippleBehavior,
    LoadingSpinner,
    MaterialCheckBox,
    MaterialTextField,
    NavigationDrawer,
    NavigationLayout,
    RectangularRippleBehavior,
)
from katrain.gui.widgets.movetree import MoveTree
from katrain.gui.widgets.panels import (
    AnalysisToggle,
    CollapsablePanel,
    CollapsablePanelHeader,
    CollapsablePanelTab,
    MenuItem,
    PlayerInfo,
    PlayerSetup,
    PlayerSetupBlock,
    StatsBox,
    Timer,
    TimerOrMoveTree,
)
from katrain.gui.widgets.selection_slider import SelectionSlider

__all__ = [
    "AnalysisToggle",
    "AutoSizedButton",
    "AutoSizedRectangleButton",
    "AutoSizedRectangleToggleButton",
    "BackgroundLabel",
    "BackgroundMixin",
    "BGBoxLayout",
    "CircleWithText",
    "CircularRippleBehavior",
    "ClickableCircle",
    "ClickableLabel",
    "CollapsablePanel",
    "CollapsablePanelHeader",
    "CollapsablePanelTab",
    "I18NFileBrowser",
    "I18NSpinner",
    "KeyValueSpinner",
    "LeftButtonBehavior",
    "LoadingSpinner",
    "MaterialCheckBox",
    "MaterialTextField",
    "MenuItem",
    "MoveTree",
    "NavigationDrawer",
    "NavigationLayout",
    "PauseButton",
    "PlayerInfo",
    "PlayerSetup",
    "PlayerSetupBlock",
    "RectangularRippleBehavior",
    "ScoreGraph",
    "ScrollableLabel",
    "SelectionSlider",
    "SizedButton",
    "SizedRectangleButton",
    "SizedRectangleToggleButton",
    "SizedToggleButton",
    "StatsBox",
    "StatsLabel",
    "TableCellLabel",
    "TableHeaderLabel",
    "TableStatLabel",
    "Timer",
    "TimerOrMoveTree",
    "ToggleButtonMixin",
    "TransparentIconButton",
    "cached_text_texture",
    "cached_texture",
    "draw_circle",
    "draw_text",
]
