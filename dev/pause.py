import kivy
from kivy.app import App
from kivy.core.text import Label as CoreLabel
from kivy.lang import Builder
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    ObjectProperty,
    OptionProperty,
    StringProperty,
)
from kivy.uix.behaviors import ButtonBehavior, ToggleButtonBehavior
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivymd.uix.behaviors import CircularRippleBehavior, RectangularRippleBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import BaseFlatButton, BasePressedButton
from kivymd.uix.navigationdrawer import MDNavigationDrawer

WHITE = [1, 1, 1, 1]


class TestBox(GridLayout):
    pass


class BackgroundMixin(Widget):
    background_color = ListProperty([0, 0, 0, 0])
    background_radius = NumericProperty(0)
    outline_color = ListProperty([0, 0, 0, 0])
    outline_width = NumericProperty(1)


class LeftButtonBehavior(ButtonBehavior):  # stops buttons etc activating on right click
    def __init__(self, **kwargs):
        self.register_event_type("on_left_release")
        self.register_event_type("on_left_press")
        super().__init__(**kwargs)

    def on_touch_down(self, touch):
        return super().on_touch_down(touch)

    def on_release(self):
        if not self.last_touch or self.last_touch.button == "left":
            self.dispatch("on_left_release")
        return super().on_release()

    def on_press(self):
        if not self.last_touch or self.last_touch.button == "left":
            self.dispatch("on_left_press")
        return super().on_press()

    def on_left_release(self):
        pass

    def on_left_press(self):
        pass


class PauseButton(LeftButtonBehavior, Widget):
    active = BooleanProperty(True)
    active_line_color = WHITE
    inactive_line_color = WHITE
    active_fill_color = ListProperty([0.5, 0.5, 0.5, 1])
    inactive_fill_color = ListProperty([1, 1, 1, 0])
    line_width = NumericProperty(5)
    fill_color = ListProperty([0.5, 0.5, 0.5, 1])
    line_color = ListProperty([0.5, 0.5, 0.5, 1])
    min_size = NumericProperty(100)

    def on_left_press(self):
        self.active = not self.active


KV = """
#:set LIGHTGREY [0.7,0.7,0.7,1]
#:set WHITE [1,1,1,1]
#:set BACKGROUND_COLOR      [16/255,18/255,32/255,1]
#:set BOX_BACKGROUND_COLOR  [46/255,65/255,88/255,1]

<BackgroundMixin>:
    canvas.before:
        Color:
            rgba: root.background_color
        RoundedRectangle:
            size: self.size
            pos: self.pos
            radius: [root.background_radius, ]
        Color:
            rgba: root.outline_color
        Line:
            rounded_rectangle: (*self.pos,self.width,self.height,root.background_radius)
            width: root.outline_width


<PauseButton>:
    min_size: min(self.height,self.width)
    line_color: root.active_line_color if self.active else root.inactive_line_color
    fill_color: root.active_fill_color if self.active else root.inactive_fill_color
     
    canvas:
        Color:
            rgba: root.fill_color
        Ellipse:
            pos: root.x + root.width/2 - root.min_size/2, root.y  + root.height/2 - root.min_size/2
            size: root.min_size,root.min_size
        Color:
            rgba: root.line_color
        Line:
            circle: root.x + root.width/2, root.y + root.height/2, root.min_size/2 - root.line_width/2
            width: root.line_width
        Line:
            points: root.x + root.width/2 - root.min_size/8, root.y + root.height/2 - root.min_size/6, root.x + root.width/2 - root.min_size/8, root.y + root.height/2 + root.min_size/6
            width: root.line_width
        Line:
            points: root.x + root.width/2 + root.min_size/8, root.y + root.height/2 - root.min_size/6, root.x + root.width/2 + root.min_size/8, root.y + root.height/2 + root.min_size/6
            width: root.line_width


<BGBoxLayout@BoxLayout+BackgroundMixin>
    background_color: BACKGROUND_COLOR
    padding: 100

                    
<TestBox>:
    canvas.before:
        Color:
            rgba: [0,1,0,1]
        Line:
            rectangle:  (*self.pos,*self.size)
            width: 1    
    cols: 2
    rows: 2
    BGBoxLayout:
        PauseButton:
            size_hint: None, None
            width: 100
            height: 200
            active: False
    BGBoxLayout:
        PauseButton:
            size_hint: None, None
            width: 200
            height: 100
    BGBoxLayout:        
        PauseButton:
            size_hint: 0.5,0.5
"""


Builder.load_string(KV)


class MyApp(MDApp):
    def __init__(self):
        super().__init__()

    def build(self):
        layout = TestBox()
        return layout


MyApp().run()
