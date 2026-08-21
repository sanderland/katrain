"""Drop-downs that show translated labels but report back stable internal keys."""

from kivy.app import App
from kivy.properties import ListProperty, NumericProperty, StringProperty
from kivy.uix.spinner import Spinner

from katrain.core.lang import i18n
from katrain.gui.theme import Theme


class KeyValueSpinner(Spinner):
    """Spinner whose displayed `values` correspond one-to-one with internal `value_refs`.

    Reading `.selected` or `.input_value` gives the key rather than the label the
    user sees, so config values do not change when the display text does.
    """

    __events__ = ["on_select"]

    value_refs = ListProperty()
    selected_index = NumericProperty(0)
    sync_height_frac = NumericProperty(1.0)  # size drop-down items to this fraction of our height
    font_name = StringProperty(Theme.DEFAULT_FONT)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.build_values()
        self.bind(size=self.update_dropdown_props, pos=self.update_dropdown_props, value_refs=self.build_values)

    @property
    def input_value(self):
        try:
            return self.value_refs[self.selected_index]
        except IndexError:
            return ""

    @property
    def selected(self):
        """`(index, key, label)` of the current selection."""
        try:
            selected = self.selected_index
            return selected, self.value_refs[selected], self.values[selected]
        except (ValueError, IndexError):
            return 0, "", ""

    def select_key(self, key):
        try:
            ix = self.value_refs.index(key)
            self.text = self.values[ix]
        except (ValueError, IndexError):
            pass

    def on_text(self, _widget, text):
        try:
            new_index = self.values.index(text)
            if new_index != self.selected_index:
                self.selected_index = new_index
                self.dispatch("on_select")
        except (ValueError, IndexError):
            pass

    def on_select(self, *args):
        pass

    def build_values(self, *_args):
        if self.value_refs and self.values:
            self.text = self.values[self.selected_index]
            self.font_name = i18n.font_name
            self.update_dropdown_props()

    def update_dropdown_props(self, *_args):
        """Match the open drop-down's items to our own height and font."""
        if not self.sync_height_frac:
            return
        container = self._dropdown.container if self._dropdown else None
        if not container:
            return
        for item in container.children[:]:
            item.height = self.height * self.sync_height_frac
            item.font_size = self.font_size
            item.font_name = self.font_name


class I18NSpinner(KeyValueSpinner):
    """`KeyValueSpinner` whose labels are the translations of its keys, refreshed on language change."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        App.get_running_app().bind(language=self.build_values)

    def build_values(self, *_args):
        self.values = [i18n._(ref) for ref in self.value_refs]
        super().build_values()
