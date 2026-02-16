from katrain.core.strings import STRINGS_EN
from katrain.gui.theme import Theme

# v2: single-language UI (English). Keep the existing `i18n._(...)` call sites
# and translation keys, but resolve them via a baked-in English string table.
DEFAULT_LANGUAGE = "en"


class Lang:
    def __init__(self, lang: str = DEFAULT_LANGUAGE):
        self.lang = DEFAULT_LANGUAGE
        self.font_name = Theme.DEFAULT_FONT

    def _(self, text: str) -> str:
        return STRINGS_EN.get(text, text)

    def switch_lang(self, _lang: str) -> None:
        # Language switching removed in v2.
        self.lang = DEFAULT_LANGUAGE


i18n = Lang(DEFAULT_LANGUAGE)


def rank_label(rank):
    if rank is None:
        return "??k"

    if rank >= 0.5:
        return f"{rank:.0f}{i18n._('strength:dan')}"
    else:
        return f"{1-rank:.0f}{i18n._('strength:kyu')}"
