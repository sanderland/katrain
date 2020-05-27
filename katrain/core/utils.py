import os
import sys
from typing import Any, List, Tuple, Callable

from kivy.event import EventDispatcher
from kivy.lang import Observable
import gettext

from kivy.properties import StringProperty
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivymd.uix.label import MDIcon

from katrain.gui.style import DEFAULT_FONT

try:
    import importlib.resources as pkg_resources
except:
    import importlib_resources as pkg_resources

OUTPUT_ERROR = -1
OUTPUT_KATAGO_STDERR = -0.5
OUTPUT_INFO = 0
OUTPUT_DEBUG = 1
OUTPUT_EXTRA_DEBUG = 2

MODE_PLAY, MODE_ANALYZE = "play", "analyze"


def var_to_grid(array_var: List[Any], size: Tuple[int, int]) -> List[List[Any]]:
    """convert ownership/policy to grid format such that grid[y][x] is for move with coords x,y"""
    ix = 0
    grid = [[]] * size[1]
    for y in range(size[1] - 1, -1, -1):
        grid[y] = array_var[ix : ix + size[0]]
        ix += size[0]
    return grid


def evaluation_class(points_lost: float, eval_thresholds: List[float]):
    i = 0
    while i < len(eval_thresholds) - 1 and points_lost < eval_thresholds[i]:
        i += 1
    return i


def find_package_resource(path):
    if path.startswith("katrain"):
        parts = path.replace("\\", "/").split("/")
        try:
            with pkg_resources.path(".".join(parts[:-1]), parts[-1]) as path_obj:
                return str(path_obj)  # this will clean up if egg etc, but these don't work anyway
        except (ModuleNotFoundError, FileNotFoundError) as e:
            print(f"File {path} not found, installation possibly broken", file=sys.stderr)
            return f"FILENOTFOUND::{path}"
    else:
        return path  # absolute path


class Lang(Observable):
    observers = []
    callbacks = []
    FONTS = {"ko": "fonts/NotoSansKR-Regular.otf"}

    def __init__(self, lang):
        super(Lang, self).__init__()
        self.switch_lang(lang)

    def _(self, text):
        if text == "":
            return ""  # just for font change
        return self.ugettext(text)

    def fbind(self, name, func, *args):
        if name == "_":
            widget, property, *_ = args[0]
            self.observers.append((widget, func, args))
            widget.font_name = self.font_name
        else:
            return super(Lang, self).fbind(name, func, *args)

    def funbind(self, name, func, *args):
        if name == "_":
            widget, *_ = args[0]
            key = (widget, func, args)
            if key in self.observers:
                self.observers.remove(key)
        else:
            return super(Lang, self).funbind(name, func, *args)

    def add_callback(self, callback_fn: Callable):
        self.callbacks.append(callback_fn)

    def switch_lang(self, lang):
        # get the right locales directory, and instantiate a gettext
        self.lang = lang
        self.font_name = self.FONTS.get(lang) or DEFAULT_FONT
        i18n_dir, _ = os.path.split(find_package_resource("katrain/i18n/__init__.py"))
        locale_dir = os.path.join(i18n_dir, "locales")
        locales = gettext.translation("katrain", locale_dir, languages=[lang])
        self.ugettext = locales.gettext

        # update all the kv rules attached to this text
        for widget, func, args in self.observers:
            try:
                func(args[0], None, None)
                widget.font_name = self.font_name
            except ReferenceError:
                pass  # proxy no longer exists
        for cb in self.callbacks:
            try:
                cb(self)
            except Exception as e:
                print(f"Failed callback on language change: {e}", file=sys.stderr)


DEFAULT_LANGUAGE = "en"
i18n = Lang(DEFAULT_LANGUAGE)


def switch_lang(lang):
    i18n.switch_lang(lang)
