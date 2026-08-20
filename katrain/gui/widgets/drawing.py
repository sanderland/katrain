"""Small helpers for drawing straight onto a widget's canvas, with texture caches.

The board and the move tree redraw from scratch on every change, so the same
handful of stone images and coordinate labels get drawn over and over; caching
their textures keeps that cheap.
"""

from kivy.core.image import Image
from kivy.core.text import Label as CoreLabel
from kivy.core.text.markup import MarkupLabel as CoreMarkupLabel
from kivy.graphics import Color, Ellipse, Rectangle
from kivy.resources import resource_find

from katrain.core.lang import i18n

_text_textures = {}
_image_textures = {}


def cached_text_texture(text, font_name, markup, **kwargs):
    key = (text, font_name, markup, *kwargs.items())
    if key not in _text_textures:
        label_cls = CoreMarkupLabel if markup else CoreLabel
        label = label_cls(text=text, bold=True, font_name=font_name or i18n.font_name, **kwargs)
        label.refresh()
        _text_textures[key] = label.texture
    return _text_textures[key]


def cached_texture(path):
    """Texture for an image file, cached by path to bypass `resource_find` lookups."""
    if path not in _image_textures:
        _image_textures[path] = Image(resource_find(path)).texture
    return _image_textures[path]


def draw_text(pos, text, font_name=None, markup=False, **kwargs):
    """Draw `text` centred on `pos`."""
    texture = cached_text_texture(text, font_name, markup, **kwargs)
    Rectangle(texture=texture, pos=(pos[0] - texture.size[0] / 2, pos[1] - texture.size[1] / 2), size=texture.size)


def draw_circle(pos, r, col):
    """Draw a filled circle of radius `r` centred on `pos`."""
    Color(*col)
    Ellipse(pos=(pos[0] - r, pos[1] - r), size=(2 * r, 2 * r))
