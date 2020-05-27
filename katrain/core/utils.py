import os
import sys
from typing import Any, List, Tuple

from kivy.event import EventDispatcher
from kivy.lang import Observable
import gettext

from kivy.properties import StringProperty
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

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


class LangFont(EventDispatcher):
    font_name = StringProperty('')


    DEFAULT_FONT = "fonts/NotoSans-Regular.ttf"
    FONTS = {'ko': "fonts/NotoSansKR-Regular.otf"}
    font_name = StringProperty('')
    def __init__(self,lang,**kwargs):
        super().__init__(**kwargs)
        self.switch_lang(lang)

    def switch_lang(self,lang):
        self.lang = lang
        self.font_name = self.FONTS.get(lang) or self.DEFAULT_FONT

class Lang(Observable):
    observers = []

    def __init__(self, lang):
        super(Lang, self).__init__()
        self.ugettext = None
        self.font = None
        self.switch_lang(lang)

    def _(self, text):
        return self.ugettext(text)

    def fbind(self, name, func, *args, **kwargs):
        if name == "_":
            self.observers.append((func, args, kwargs))
        else:
            return super(Lang, self).fbind(name, func, *args, **kwargs)

    def funbind(self, name, func, *args, **kwargs):
        if name == "_":
            key = (func, args, kwargs)
            print("funbind", key in self.observers)
            if key in self.observers:
                self.observers.remove(key)
        else:
            return super(Lang, self).funbind(name, func, *args, **kwargs)

    def switch_lang(self, lang):
        # get the right locales directory, and instantiate a gettext
        self.lang = lang
        i18n_dir, _ = os.path.split(find_package_resource("katrain/i18n/__init__.py"))
        locale_dir = os.path.join(i18n_dir, "locales")
        locales = gettext.translation("katrain", locale_dir, languages=[lang])
        self.ugettext = locales.gettext

        # update all the kv rules attached to this text
        for func, args, kwargs in self.observers:
            try:
                func(args[0], None, None)
            except ReferenceError:
                pass  # proxy no longer exists



DEFAULT_LANGUAGE = "en"
i18n = Lang(DEFAULT_LANGUAGE)
i18n_font = LangFont(DEFAULT_LANGUAGE)

def switch_lang(lang):
    i18n.switch_lang(lang)
    i18n_font.switch_lang(lang)
