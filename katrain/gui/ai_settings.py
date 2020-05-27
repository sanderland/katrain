from kivy.clock import Clock
from kivy.uix.popup import Popup
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDLabel

from katrain.core.utils import OUTPUT_DEBUG, OUTPUT_ERROR
from katrain.gui.kivyutils import SizedButton, LightHelpLabel, ScaledLightLabel, StyledSpinner
from katrain.gui.popups import QuickConfigGui, ConfigPopup, InputParseError

KV = """
<ConfigAIPopupContents>:
    orientation: 'vertical'
    rules_spinner: rules_spinner
    info: info
    restart: restart
    GridLayout:
        size_hint: 1, 0.8
        rows: 6
        cols: 3
        spacing: 2
        padding: 2
        ScaledLightLabel:
            text: "Size"
        LabelledTextInput:
            text: '19'
            font_size: 0.5*self.size[1]
            padding: 7, 0.2*self.size[1]
            input_property: 'SZ'
        BoxLayout:
            spacing: 1
            QuickInputButton:
                text: '9'
            QuickInputButton:
                text: '13'
            QuickInputButton:
                text: '19'
        ScaledLightLabel:
            text: "Handicap"
        LabelledIntInput:
            text: '0'
            input_property: 'HA'
        BoxLayout:
            spacing: 1
            QuickInputButton:
                text: '0'
                on_left_press: if not self.last_touch or self.last_touch.button=="left": km.text='6.5'
            QuickInputButton:
                text: '2'
                on_left_press: if not self.last_touch or self.last_touch.button=="left": km.text='0.5'
            QuickInputButton:
                text: '9'
                on_left_press: if not self.last_touch or self.last_touch.button=="left": km.text='0.5'
        ScaledLightLabel:
            text: "Komi"
        LabelledFloatInput:
            text: '6.5'
            id: km
            input_property: 'KM'
        BoxLayout:
            spacing: 1
            QuickInputButton:
                text: '0.5'
            QuickInputButton:
                text: '5.5'
            QuickInputButton:
                text: '6.5'
        ScaledLightLabel:
            text: "Ruleset"
        LabelledSpinner:
            input_property: 'RU'
            id: rules_spinner
        Label:
        ScaledLightLabel:
            text: 'Clear cache'
        CheckBox:
            color: WHITE
            id: restart
        ScaledLightLabel:
            font_size: 0.35*self.size[1]
            text: 'avoids replaying\nidentical games'
        LightHelpLabel:
            text: "Use x:y (e.g. 19:9) to play on a non-square board."
            size_hint: 1,2
            text_size: self.width-6, None
            font_size: self.size[1]/6
            id: info
        LightHelpLabel:
            text: "Note that handicaps above 9 are not supported on non-square boards."
            font_size: self.size[1]/6
            text_size: self.width-6, None
            id: info
        StyledButton:
            halign: 'center'
            text: 'Start\nGame'
            font_size: 0.3 * self.size[1]
            on_left_press: if not self.last_touch or self.last_touch.button=="left": root.new_game()

"""


class ConfigAIPopupContents(QuickConfigGui):
    def __init__(self, katrain, popup: Popup):
        self.settings = {"engine": katrain.config("engine")}
        super().__init__(katrain, popup, settings=self.settings)
        Clock.schedule_once(self.build, 0)

    def build(self, _):
        ais = list(self.settings.keys())

        top_bl = MDBoxLayout()
        top_bl.add_widget(ScaledLightLabel(text="Select AI to configure:"))
        ai_spinner = StyledSpinner(values=ais, text=ais[0])
        ai_spinner.fbind("text", lambda _, text: self.build_ai_options(text))
        top_bl.add_widget(ai_spinner)
        self.add_widget(top_bl)
        self.options_grid = MDGridLayout(cols=2, rows=max(len(v) for v in self.settings.values()) - 1, size_hint=(1, 7.5), spacing=1)  # -1 for help in 1 col
        bottom_bl = MDBoxLayout(spacing=2)
        self.info_label = MDLabel()
        bottom_bl.add_widget(SizedButton(text=f"Apply", on_press=lambda _: self.update_config(False)))  # raised?
        bottom_bl.add_widget(self.info_label)
        bottom_bl.add_widget(SizedButton(text=f"Apply and Save", on_press=lambda _: self.update_config(True)))
        self.add_widget(self.options_grid)
        self.add_widget(bottom_bl)
        self.build_ai_options(ais[0])

    def build_ai_options(self, mode):
        mode_settings = self.settings[mode]
        self.options_grid.clear_widgets()
        self.options_grid.add_widget(LightHelpLabel(size_hint=(1, 4), padding=(2, 2), text=mode_settings.get("_help_left", "")))
        self.options_grid.add_widget(LightHelpLabel(size_hint=(1, 4), padding=(2, 2), text=mode_settings.get("_help_right", "")))
        for k, v in mode_settings.items():
            if not k.startswith("_"):
                self.options_grid.add_widget(ScaledLightLabel(text=f"{k}"))
                self.options_grid.add_widget(ConfigPopup.type_to_widget_class(v)(text=str(v), input_property=f"{mode}/{k}"))
        for _ in range(self.options_grid.rows * self.options_grid.cols - len(self.options_grid.children)):
            self.options_grid.add_widget(ScaledLightLabel(text=f""))
        self.set_properties(self, self.settings)

    def update_config(self, save_to_file=False):
        try:
            for k, v in self.collect_properties(self).items():
                k1, k2 = k.split("/")
                if self.settings[k1][k2] != v:
                    self.settings[k1][k2] = v
                    self.katrain.log(f"Updating setting {k} = {v}", OUTPUT_DEBUG)
            if save_to_file:
                self.katrain.save_config()
            self.popup.dismiss()
        except InputParseError as e:
            self.info_label.text = str(e)
            self.katrain.log(e, OUTPUT_ERROR)
            return
        self.popup.dismiss()
