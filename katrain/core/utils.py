import os
import sys
from numbers import Number
from typing import List, Tuple, Callable, TypeVar
from kivy.lang import Observable
import gettext

from katrain.gui.style import DEFAULT_FONT

try:
    import importlib.resources as pkg_resources
except:
    import importlib_resources as pkg_resources

T = TypeVar("T")


def var_to_grid(array_var: List[T], size: Tuple[int, int]) -> List[List[T]]:
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
        return os.path.abspath(os.path.expanduser(path))  # absolute path


class Lang(Observable):
    observers = []
    callbacks = []
    FONTS = {"ko": "fonts/NotoSansKR-Regular.otf", "haha": "fonts/NotoSansKR-Regular.otf"}

    def __init__(self, lang):
        super(Lang, self).__init__()
        self.switch_lang(lang)

    def _(self, text):
        return self.ugettext(text)

    def set_widget_font(self, widget):
        widget.font_name = self.font_name
        for sub_widget in [getattr(widget, "_hint_lbl", None), getattr(widget, "_msg_lbl", None)]:  # MDText
            if sub_widget:
                sub_widget.font_name = self.font_name

    def fbind(self, name, func, *args):
        if name == "_":
            widget, property, *_ = args[0]
            self.observers.append((widget, func, args))
            try:
                self.set_widget_font(widget)
            except Exception as e:
                print(e)
                # pass
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
                self.set_widget_font(widget)
            except ReferenceError:
                pass  # proxy no longer exists
        for cb in self.callbacks:
            try:
                cb(self)
            except Exception as e:
                print(f"Failed callback on language change: {e}", file=sys.stderr)


DEFAULT_LANGUAGE = "en"
i18n = Lang(DEFAULT_LANGUAGE)
