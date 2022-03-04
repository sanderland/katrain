import gettext
import os
import sys

from kivy._event import Observable

from katrain.core.utils import find_package_resource
from katrain.gui.theme import Theme


class Lang(Observable):
    observers = []
    callbacks = []
    FONTS = {"jp": "NotoSansJP-Regular.otf", "tr": "NotoSans-Regular.ttf"}

    def __init__(self, lang):
        super(Lang, self).__init__()
        self.lang = None
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

    def switch_lang(self, lang):
        if lang == self.lang:
            return
        # get the right locales directory, and instantiate a gettext
        self.lang = lang
        self.font_name = self.FONTS.get(lang) or Theme.DEFAULT_FONT
        i18n_dir, _ = os.path.split(find_package_resource("katrain/i18n/__init__.py"))
        locale_dir = os.path.join(i18n_dir, "locales")
        locales = gettext.translation("katrain", locale_dir, languages=[lang, DEFAULT_LANGUAGE])
        self.ugettext = locales.gettext

        # update all the kv rules attached to this text
        for widget, func, args in self.observers:
            try:
                func(args[0], None, None)
                self.set_widget_font(widget)
            except ReferenceError:
                pass  # proxy no longer exists
            except Exception as e:
                print("Error in switching languages", e)
        for cb in self.callbacks:
            try:
                cb(self)
            except Exception as e:
                print(f"Failed callback on language change: {e}", file=sys.stderr)


DEFAULT_LANGUAGE = "en"
i18n = Lang(DEFAULT_LANGUAGE)


def rank_label(rank):
    if rank is None:
        return "??k"

    if rank >= 0.5:
        return f"{rank:.0f}{i18n._('strength:dan')}"
    else:
        return f"{1-rank:.0f}{i18n._('strength:kyu')}"
