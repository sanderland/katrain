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


# -- resizeable buttons
class SizedButton(LeftButtonBehavior, RectangularRippleBehavior, BasePressedButton, BaseFlatButton, BackgroundMixin):  # avoid baserectangular for sizing
    text = StringProperty("")
    text_color = ListProperty(WHITE)
    text_size = ListProperty([100, 100])
    halign = OptionProperty("center", options=["left", "center", "right", "justify", "auto"])
    label = ObjectProperty(None)
    padding_x = NumericProperty(6)
    padding_y = NumericProperty(0)
    fsz = NumericProperty(None)


class AutoSizedButton(SizedButton):
    pass


class ToggleButtonMixin(ToggleButtonBehavior):
    inactive_outline_color = ListProperty([0.5, 0.5, 0.5, 0])
    active_outline_color = ListProperty([1, 1, 1, 0])
    inactive_background_color = ListProperty([0.5, 0.5, 0.5, 1])
    active_background_color = ListProperty([1, 1, 1, 1])


class SizedRectangleButton(SizedButton):
    pass


class SizedRectangleToggleButton(ToggleButtonMixin, SizedRectangleButton):
    pass


class AutoSizedRectangleButton(AutoSizedButton):
    pass


class AutoSizedRectangleToggleButton(ToggleButtonMixin, AutoSizedRectangleButton):
    pass


class TransparentIconButton(CircularRippleBehavior, Button):
    icon_size = ListProperty([25, 25])
    icon = StringProperty("")


KV = """
#:set LIGHTGREY [0.7,0.7,0.7,1]
#:set WHITE [1,1,1,1]

#:set BUTTON_INACTIVE_COLOR LIGHTGREY
#:set BACKGROUND_COLOR      [16/255,18/255,32/255,1]
#:set BOX_BACKGROUND_COLOR  [46/255,65/255,88/255,1]
#:set TEXT_COLOR            WHITE
<Label>:
    canvas.before:
        Color:
            rgba: [1,0,0,1]
        Line:
            rectangle:  (*self.pos,*self.size)
            width: 1

# mixins
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

<SizedButton>:
    ripple_duration_in_slow: 0.6
    text_color: WHITE
    background_color: BOX_BACKGROUND_COLOR
    label: label
    text_size: root.size
    onlytext: ''
    on_press: print('size: {}\\ntexture_size: {}\\ntext_size: {} - font {} - {} - {} ?\\npos: {} - halign {}'.format(label.size,label.texture_size,label.text_size,label.font_size,root.font_size,0.6 * self.height / len(self.label.text.split('\\n')),label.pos,label.halign),self.label.text.split('\\n'))
    Label:
        id: label
        padding: [root.padding_x,root.padding_y]
        color: root.text_color
        font_size: 0.6 * self.height / len(self.text.split('\\n')) if root.fsz is None else root.fsz
        on_font_size: print(args,self.font_size,self.text)
        halign: root.halign
        text: 'size: {}\\ntexture_size: {}\\ntext_size: {}\\npos: {}halign {}\\n{}'.format(self.size,self.texture_size,self.text_size,self.pos,self.halign,root.text) if not root.onlytext else root.onlytext

<AutoSizedButton>:
    width: root.label.texture_size[0]

<SizedToggleButton>
    inactive_background_color: BACKGROUND_COLOR
    active_background_color: BOX_BACKGROUND_COLOR
    background_color: self.active_background_color if self.state=='down' else self.inactive_background_color
    outline_color: self.active_outline_color if self.state=='down' else self.inactive_outline_color

<SizedRectangleButton>:
    outline_color: WHITE
    text_color: self.outline_color

<SizedRectangleToggleButton>:
    inactive_outline_color: BUTTON_INACTIVE_COLOR
    active_outline_color: WHITE
    text_color: self.outline_color

<AutoSizedRectangleButton>: # only wants height
    outline_color: WHITE
    text_color: self.outline_color


<AutoSizedRoundedRectangleButton@AutoSizedRectangleButton>:
    background_radius: self.height/3.5
    halign: 'left'

<PassBtn@AutoSizedRoundedRectangleButton>:
    id: pass_btn
    onlytext: 'Pass'
    background_radius: 10
    height: 50

<BGBoxLayout@BoxLayout+BackgroundMixin>
    background_color: BACKGROUND_COLOR
    padding: 100

<TransparentIconButton>:
    background_normal: ''
    background_color: (0,0,0,0)
    image: image
    Image:
        id: image
        size: root.icon_size
        pos: [root.pos[i] + (root.size[i] - root.icon_size[i])/2 for i in [0,1]]
        source: root.icon
        mipmap: True

                    
<TestBox>:
    canvas.before:
        Color:
            rgba: [0,1,0,1]
        Line:
            rectangle:  (*self.pos,*self.size)
            width: 1    
    cols: 2
    rows: 3
    BGBoxLayout:
        SizedButton:
            text: 'SizedButton'
            height: 125
            width: 300
    BGBoxLayout:
        AutoSizedRectangleButton:
            text: 'AutoSizedRectangleButton'
            size_hint_y: None
            height: 150
    BGBoxLayout:        
        SizedRectangleButton:
            text: 'SizedRectangleButton'
            height: 125
            width: 300
            halign: 'left'
            background_radius: 25
    BGBoxLayout:
        AutoSizedRoundedRectangleButton:
            text: 'AutoSizedRectangleButton'
            halign: 'left'
            size_hint_y: None
            height: 150
    BGBoxLayout:
        PassBtn:
"""


Builder.load_string(KV)


class MyApp(MDApp):
    def __init__(self):
        super().__init__()

    def build(self):
        layout = TestBox()
        return layout


MyApp().run()
