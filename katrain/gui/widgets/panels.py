"""The composite panels of the main window: player setup, clock, menu items and tab panels."""

from kivy.app import App
from kivy.clock import Clock
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    ObjectProperty,
    OptionProperty,
    StringProperty,
)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from katrain.core.constants import (
    AI_STRATEGIES_RECOMMENDED_ORDER,
    GAME_TYPES,
    MODE_PLAY,
    PLAYER_AI,
    PLAYER_HUMAN,
    PLAYING_NORMAL,
    PLAYING_TEACHING,
)
from katrain.core.lang import i18n
from katrain.gui.theme import Theme
from katrain.gui.widgets.base import BackgroundMixin, BGBoxLayout, LeftButtonBehavior
from katrain.gui.widgets.buttons import AutoSizedRectangleToggleButton, TransparentIconButton
from katrain.gui.widgets.material import RectangularRippleBehavior


class PlayerSetup(BoxLayout):
    """Human/AI choice plus the matching sub-type drop-down, for one colour."""

    player = OptionProperty("B", options=["B", "W"])
    mode = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.player_subtype_ai.value_refs = AI_STRATEGIES_RECOMMENDED_ORDER
        self.player_subtype_human.value_refs = GAME_TYPES
        self.setup_options()

    def setup_options(self, *_args):
        if self.player_type.selected[1] == self.mode:
            return
        self.mode = self.player_type.selected[1]
        self.update_global_player_info()

    @property
    def player_type_dump(self):
        subtype = self.player_subtype_ai if self.mode == PLAYER_AI else self.player_subtype_human
        return {"player_type": self.player_type.selected[1], "player_subtype": subtype.selected[1]}

    def update_widget(self, player_type, player_subtype):
        self.player_type.select_key(player_type)  # should trigger setup options
        if self.mode == PLAYER_AI:
            self.player_subtype_ai.select_key(player_subtype)  # should trigger setup options
        else:
            self.player_subtype_human.select_key(player_subtype)  # should trigger setup options

    def update_global_player_info(self):
        if self.parent and self.parent.update_global:
            katrain = App.get_running_app().gui
            if katrain.game and katrain.game.current_node:
                katrain.update_player(self.player, **self.player_type_dump)


class PlayerSetupBlock(BoxLayout):
    """The black and white `PlayerSetup` widgets side by side.

    Several of these exist at once (the hamburger menu and the new game popup), and
    `INSTANCES` lets the app push game state changes to all of them.
    """

    players = ObjectProperty(None)
    black = ObjectProperty(None)
    white = ObjectProperty(None)
    update_global = BooleanProperty(False)
    INSTANCES = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.black = PlayerSetup(player="B")
        self.white = PlayerSetup(player="W")
        self.players = {"B": self.black, "W": self.white}
        self.add_widget(self.black)
        self.add_widget(self.white)
        PlayerSetupBlock.INSTANCES.append(self)

    def swap_players(self):
        player_dump = {bw: p.player_type_dump for bw, p in self.players.items()}
        for bw in "BW":
            self.update_player_params(bw, player_dump["B" if bw == "W" else "W"])

    def update_player_params(self, bw, params):
        self.players[bw].update_widget(**params)

    def update_player_info(self, bw, player_info):  # update sub widget based on gui state change
        Clock.schedule_once(
            lambda _dt: self.players[bw].update_widget(
                player_type=player_info.player_type, player_subtype=player_info.player_subtype
            ),
            -1,
        )


class PlayerInfo(BoxLayout, BackgroundMixin):
    """Name, rank and captures of one player, above the board controls."""

    captures = ObjectProperty(0)
    player = OptionProperty("B", options=["B", "W"])
    player_type = StringProperty("Player")
    player_subtype = StringProperty("")
    name = StringProperty("", allownone=True)
    rank = StringProperty("", allownone=True)
    active = BooleanProperty(True)
    alignment = StringProperty("right")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(player_type=self.set_label, player_subtype=self.set_label, name=self.set_label, rank=self.set_label)

    def set_label(self, *_args):
        """Show the player's name where we have one, and otherwise what they are."""
        if not self.subtype_label:  # building
            return
        show_player_name = self.name and self.player_type == PLAYER_HUMAN and self.player_subtype == PLAYING_NORMAL
        text = self.name if show_player_name else i18n._(self.player_subtype)
        if (
            self.rank
            and self.player_subtype != PLAYING_TEACHING
            and (show_player_name or self.player_type == PLAYER_AI)
        ):
            text += " ({})".format(self.rank)
        self.subtype_label.text = text


class TimerOrMoveTree(BoxLayout):
    """Holds both the clock and the move tree, showing whichever suits the current mode."""

    mode = StringProperty(MODE_PLAY)


class Timer(BGBoxLayout):
    state = ListProperty([30, 5, 1])  # [main time left, periods left, time left in current period]
    timeout = BooleanProperty(False)


class AnalysisToggle(BoxLayout):
    """Check box with a clickable label next to it, in the analysis controls bar."""

    text = StringProperty("")
    default_active = BooleanProperty(False)
    font_name = StringProperty(Theme.DEFAULT_FONT)
    disabled = BooleanProperty(False)

    def trigger_action(self, *_args, **_kwargs):
        return self.checkbox._do_press()

    def activate(self, *_args):
        self.checkbox.active = True

    @property
    def active(self):
        return self.checkbox.active


class MenuItem(RectangularRippleBehavior, LeftButtonBehavior, BoxLayout, BackgroundMixin):
    """Row of icon, label and keyboard shortcut, in the hamburger and analysis menus."""

    __events__ = ["on_action", "on_close"]
    icon = StringProperty("")
    text = StringProperty("")
    shortcut = StringProperty("")
    font_name = StringProperty(Theme.DEFAULT_FONT)
    content_width = NumericProperty(100)

    def on_left_release(self):
        self.anim_complete()  # kill ripple, as the menu is about to disappear
        self.dispatch("on_close")
        self.dispatch("on_action")

    def on_action(self):
        pass

    def on_close(self):
        pass


class StatsBox(BoxLayout, BackgroundMixin):
    winrate = StringProperty("...")
    score = StringProperty("...")
    points_lost = NumericProperty(None, allownone=True)
    player = StringProperty("")


class CollapsablePanelHeader(BoxLayout):
    pass


class CollapsablePanelTab(AutoSizedRectangleToggleButton):
    pass


class CollapsablePanel(BoxLayout):
    """Panel with a row of independently toggleable tabs, which collapses to just that row.

    Widgets added from `.kv` become the panel :attr:`contents`, shown below the tabs
    while the panel is open. Which tabs are on is reported through the `on_option_state`
    event as a `{option: bool}` dict; the panel does not interpret them itself.
    """

    __events__ = ["on_option_state"]

    options = ListProperty([])  # internal keys of the tabs
    option_labels = ListProperty([])  # tab text; defaults to the translation of `tab:<option>`
    option_colors = ListProperty([])
    option_active = ListProperty([])
    options_height = NumericProperty(25)
    options_spacing = NumericProperty(6)

    contents = ListProperty([])
    content_height = NumericProperty(100)
    size_hint_y_open = NumericProperty(None)  # total height inc tabs, overrides content_height
    closed_label = StringProperty("Closed Panel")

    state = OptionProperty("open", options=["open", "close"])
    open_icon = "Next-5.png"
    close_icon = "Previous-5.png"

    def __init__(self, **kwargs):
        self.header = CollapsablePanelHeader(size_hint_y=None, padding=[1, 0, 0, 0])
        self.collapse_button = TransparentIconButton(size_hint_x=None, on_press=lambda *_args: self.set_state("toggle"))
        self.option_buttons = []
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.bind(
            options=self._rebuild_tabs,
            option_labels=self._rebuild_tabs,
            option_colors=self._rebuild_tabs,
            option_active=self._rebuild_tabs,
            options_height=self._rebuild_tabs,
            options_spacing=self._rebuild_tabs,
        )
        self.bind(state=self._on_state, content_height=self._update_height)
        App.get_running_app().bind(language=lambda *_args: Clock.schedule_once(self._rebuild_tabs, 0))
        self._rebuild_tabs()

    @property
    def option_state(self):
        return dict(zip(self.options, self.option_active))

    def set_option_state(self, state_dict):
        """Turn tabs on or off, e.g. when restoring the saved UI state."""
        for ix, option in enumerate(self.options[: len(self.option_buttons)]):
            if option in state_dict:
                self.option_active[ix] = bool(state_dict[option])
                self.option_buttons[ix].state = "down" if state_dict[option] else "normal"
        self._notify_option_state()

    def set_state(self, state="toggle"):
        self.state = ("close" if self.state == "open" else "open") if state == "toggle" else state

    def on_option_state(self, options):
        pass

    # -- internals

    def _on_state(self, *_args):
        self._rebuild()
        self._notify_option_state()

    def _on_tab_toggled(self, ix):
        self.option_active[ix] = self.option_buttons[ix].state == "down"
        self._notify_option_state()

    def _notify_option_state(self):
        if self.state == "open":
            self.dispatch("on_option_state", self.option_state)

    def _rebuild_tabs(self, *_args):
        """Recreate the tab buttons, e.g. after the options or the language changed."""
        labels = self.option_labels or [i18n._(f"tab:{option}") for option in self.options]
        self.option_buttons = []
        for ix, (label, color, active) in enumerate(zip(labels, self.option_colors, self.option_active)):
            button = CollapsablePanelTab(
                text=label,
                font_name=i18n.font_name,
                active_outline_color=color,
                height=self.options_height,
                state="down" if active else "normal",
            )
            button.bind(state=lambda *_args, _ix=ix: self._on_tab_toggled(_ix))
            self.option_buttons.append(button)
        self._rebuild()

    def _rebuild(self, *_args):
        """Fill in the header row, and the contents below it while the panel is open."""
        open_ = self.state == "open"
        self.header.height = self.options_height
        self.header.spacing = self.options_spacing
        self.collapse_button.icon = self.open_icon if open_ else self.close_icon
        self.collapse_button.icon_size = [0.5 * self.options_height, 0.5 * self.options_height]
        self.collapse_button.width = 0.75 * self.options_height

        self.header.clear_widgets()
        if open_:
            for button in self.option_buttons:
                self.header.add_widget(button)
            self.header.add_widget(Label())  # spacer, pushes the collapse button to the right
        else:
            self.header.add_widget(
                Label(
                    text=i18n._(self.closed_label),
                    font_name=i18n.font_name,
                    halign="right",
                    height=self.options_height,
                )
            )
        self.header.add_widget(self.collapse_button)

        super().clear_widgets()
        super().add_widget(self.header)
        if open_:
            for widget in self.contents:
                super().add_widget(widget)
        self._update_height()

    def _update_height(self, *_args):
        if self.state == "open" and self.contents:
            if self.size_hint_y_open is not None:
                self.height, self.size_hint_y = 1, self.size_hint_y_open
            else:
                self.height, self.size_hint_y = self.content_height + self.options_height, None
        else:
            self.height, self.size_hint_y = self.header.height, None

    def add_widget(self, widget, *_args, **_kwargs):
        """Children declared in `.kv` become panel contents, shown only while open."""
        self.contents.append(widget)
        self._rebuild()
