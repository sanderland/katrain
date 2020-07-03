import math

import kivy
from kivy.app import App
from kivy.core.image import Texture
from kivy.factory import Factory
from kivy.graphics.vertex_instructions import Ellipse
from kivy.lang import Builder
from kivy.properties import NumericProperty, ObjectProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget


class MyWidget(Widget):
    pass


class MyTexture(Widget):
    radius = NumericProperty(100)
    texture = ObjectProperty(None, allownone=True)

    #    @staticmethod
    #    def generate_texture():

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(size=self.redraw)
        self.cbuffer = None
        self.redraw()

    @staticmethod
    def draw_circle(height, width):

        r = min(height / 2, width / 2) - 5
        center = r

        arr = [[[0, 1, 0, 1] for _ in range(height)] for _ in range(width)]
        n = 1000
        for i in range(n):
            dr = 2 * math.pi * i / n
            x, y = round(center + r * math.cos(dr)), round(center + r * math.sin(dr))
            arr[y][x] = [1, 0, 0, 1]
        l = sum([sum(r, []) for r in arr], [])
        return "".join(chr(round(a*255)) for a in l).encode()

    def redraw(self, *args):
        width, height = self.size
        self.cbuffer = self.draw_circle(width, height)  # b"\xff\x66\x99\xff" * width * height
        self.texture = Texture.create(size=(width, height), colorfmt="rgba", bufferfmt="ubyte")
        self.texture.add_reload_observer(self.populate_texture)
        self.populate_texture(self.texture)

    def populate_texture(self, texture):
        texture.blit_buffer(self.cbuffer, colorfmt="rgba", bufferfmt="ubyte")


KV = """

<MyTexture>:
    canvas.before:
        Rectangle:
            pos: root.pos
            texture: root.texture

<MyWidget>:
    canvas:
        Color:
            rgba: (1,0,0,1)
        Ellipse:
            pos: 100,100
            size: 50,50
    MyTexture:
        pos: 300,300
        size: 100,200            
"""
Builder.load_string(KV)


class MyApp(App):
    def build(self):
        return MyWidget()


if __name__ == "__main__":
    MyApp().run()
