import kivy
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label


class TestBox(GridLayout):
    pass


KV = """
<Label>:
    valign: 'top'
    halign: 'right'
    xtext: ''
    text: 'size: {}\\ntexture_size: {}\\ntext_size: {}\\npos: {}\\n{}'.format(self.size,self.texture_size,self.text_size,self.pos,root.xtext)
    canvas.before:
        Color:
            rgba: [1,0,0,1]
        Line:
            rectangle:  (*self.pos,*self.size)
            width: 1


                    
<TestBox>:
    canvas.before:
        Color:
            rgba: [0,1,0,1]
        Line:
            rectangle:  (*self.pos,*self.size)
            width: 1    
    cols: 2
    rows: 2
    Label:
        xtext: 'size=texturesize'
        size: self.texture_size
    Label:
        xtext: 'texturesize=size'
        texture_size: self.size
    Label:
        xtext: 'textsize=size'
        text_size: self.size
    Label:
        xtext: 'texturesize=textsize=size'
        texture_size: self.size
        text_size: self.size

   
"""


Builder.load_string(KV)


class MyApp(App):
    def build(self):
        layout = TestBox()
        return layout


MyApp().run()
