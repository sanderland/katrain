import kivy
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label


class TestBox(BoxLayout):
    pass


KV = """
<TestBox>:
    canvas.before:
        Color:
            rgba: [0,1,0,1]
        Line:
            rectangle:  (*self.pos,*self.size)
            width: 1    
    FileChooserListView:
        id: filesel
        multiselect: False
        filters: ["*.sgf"]
        path: "."
        size_hint: 1,0.5

"""

Builder.load_string(KV)


class MyApp(App):
    def build(self):
        layout = TestBox()
        return layout


MyApp().run()
