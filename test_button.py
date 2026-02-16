"""Minimal test app to debug SizedButton text positioning."""
from kivy.app import App
from kivy.lang import Builder
from kivy.resources import resource_add_path
import os, katrain

resource_add_path(os.path.join(os.path.dirname(katrain.__file__), "fonts"))
resource_add_path(os.path.join(os.path.dirname(katrain.__file__), "img"))

import katrain.gui.kivyutils  # noqa: registers widgets
Builder.load_file("katrain/gui.kv")

KV = """
BoxLayout:
    orientation: 'vertical'
    padding: 20
    spacing: 10
    canvas.before:
        Color:
            rgba: 0.14, 0.19, 0.24, 1
        Rectangle:
            pos: self.pos
            size: self.size

    SizedRectangleButton:
        text: "SizedButton"
        size_hint_y: None
        height: 50

    AutoSizedRectangleButton:
        text: "AutoSized"
        size_hint_y: None
        height: 50

    Label:
        text: "Plain Kivy Label (for comparison)"
        size_hint_y: None
        height: 50
        text_size: self.size
        halign: 'center'
        valign: 'middle'
        color: 1, 1, 1, 1
        canvas.before:
            Color:
                rgba: 0.18, 0.25, 0.34, 1
            Rectangle:
                pos: self.pos
                size: self.size
"""


class TestApp(App):
    def build(self):
        return Builder.load_string(KV)


TestApp().run()
