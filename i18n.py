import os
import polib
import sys
import re
from collections import defaultdict

localedir = "katrain/i18n/locales"
locales = set(os.listdir(localedir))
print("locales found:", locales)

strings_to_langs = defaultdict(dict)
lang_to_strings = defaultdict(set)

DEFAULT_LANG = "en"

errors = False

po = {}
pofile = {}
for lang in locales:
    pofile[lang] = os.path.join(localedir, lang, "LC_MESSAGES", "katrain.po")
    po[lang] = polib.pofile(pofile[lang])
    for entry in po[lang].translated_entries():
        if "TODO" in entry.comment:
            print(lang, "/", entry.msgid, "is TODO")
        else:
            strings_to_langs[entry.msgid][lang] = entry.msgstr
        lang_to_strings[lang].add(entry.msgid)


for lang in locales:
    for msgid in strings_to_langs.keys() - lang_to_strings[lang]:
        if lang == DEFAULT_LANG:
            print("Message id", msgid, "found as ", strings_to_langs[msgid], "but missing in default", DEFAULT_LANG)
            errors = True
        elif DEFAULT_LANG in strings_to_langs[msgid]:
            print("Message id", msgid, "missing in ", lang, "-> Adding it from", DEFAULT_LANG)
            copied_msg = strings_to_langs[msgid][DEFAULT_LANG]
            if lang == "haha":
                copied_msg = re.sub(r"[a-zA-Z]{1,2}", "ㅋ", copied_msg)
            entry = polib.POEntry(msgid=msgid, msgstr=copied_msg, comment="TODO")
            po[lang].append(entry)
            errors = True
        else:
            print(f"MISSING IN DEFAULT AND {lang}", strings_to_langs[msgid])
            errors = True
    po[lang].save(pofile[lang])
    mofile = pofile[lang].replace(".po", ".mo")
    po[lang].save_as_mofile(mofile)
    print("Fixed", pofile[lang], "and converted ->", mofile)


sys.exit(int(errors))
