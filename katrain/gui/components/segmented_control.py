from kivy.metrics import dp
from kivy.properties import ListProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout

from katrain.gui.components.buttons import KtToggleButton
from katrain.gui.theme import Theme


class KtSegmentButton(KtToggleButton):
    """A single segment inside `KtSegmentedControl`."""

    value = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Segments want a clear active/inactive affordance.
        self.inactive_fill_color = Theme.SURFACE_BG
        self.inactive_text_color = Theme.BUTTON_INACTIVE_COLOR


class KtSegmentedControl(BoxLayout):
    """A small segmented control built from toggle buttons.

    `options` is a list of dicts with either:
    - {"id": "play", "text_key": "btn:Play"}
    - {"id": "analysis", "text": "Analysis"}
    """

    options = ListProperty([])
    selected = StringProperty("")
    select_callback = ObjectProperty(None, allownone=True)
    group = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.spacing = kwargs.get("spacing", dp(Theme.SPACING_XS))
        self.padding = kwargs.get("padding", [0, 0, 0, 0])

        if not self.group:
            self.group = f"kt_segment_{id(self)}"

        self.bind(options=self._rebuild, group=self._rebuild, selected=self._sync_selected)
        self._rebuild()

    def _rebuild(self, *_args):
        self.clear_widgets()

        if not self.options:
            return

        if not self.group:
            self.group = f"kt_segment_{id(self)}"

        for opt in self.options:
            value = str(opt.get("id", ""))
            btn = KtSegmentButton(value=value, group=self.group)
            btn.allow_no_selection = False

            if "text_key" in opt and opt["text_key"]:
                btn.text_key = opt["text_key"]
            else:
                btn.text = opt.get("text", value)

            btn.disabled = bool(opt.get("disabled", False))
            btn.variant = opt.get("variant", "default")
            btn.bind(state=self._on_button_state)
            self.add_widget(btn)

        if not self.selected:
            self.selected = str(self.options[0].get("id", ""))
        else:
            self._sync_selected()

    def _sync_selected(self, *_args):
        for child in self.children:
            if isinstance(child, KtSegmentButton):
                child.state = "down" if child.value == self.selected else "normal"

    def _on_button_state(self, button: KtSegmentButton, state: str):
        if state != "down":
            return

        if self.selected == button.value:
            return

        self.selected = button.value
        if self.select_callback:
            self.select_callback(button.value)
