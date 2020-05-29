from kivy.clock import Clock
from kivy.lang import Builder

from kivymd.app import MDApp
from kivymd.uix.textfield import MDTextField


class MyMDTextField(MDTextField):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(lambda dt: self.check_error(self.text), 0)

    def check_error(self, text):
        self.error = text != "correct"
        print("checking error for", text, "->", self.error)

    def on_text(self, widget, text):
        self.check_error(text)
        return super().on_text(widget, text)


KV = """
BoxLayout:
    padding: "10dp"

    MyMDTextField:
        id: text_field_error
        text: 'incorrect'
        hint_text: "Helper text on error (press 'Enter')"
        helper_text: "There will always be a mistake"
        helper_text_mode: "on_error"
        pos_hint: {"center_y": .5}
"""


class Test(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.screen = Builder.load_string(KV)

    def build(self):
        return self.screen


Test().run()
