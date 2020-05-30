import os
import polib
import sys
import re
from collections import defaultdict

localedir = "katrain/i18n/locales"
locales = set(os.listdir(localedir))
print("locales found:", locales)

strings_to_langs = defaultdict(dict)
strings_to_keys = defaultdict(dict)
lang_to_strings = defaultdict(set)

DEFAULT_LANG = "en"

errors = False

po = {}
pofile = {}
num_todo = defaultdict(int)

for lang in locales:
    pofile[lang] = os.path.join(localedir, lang, "LC_MESSAGES", "katrain.po")
    po[lang] = polib.pofile(pofile[lang])
    for entry in po[lang].translated_entries():
        if "TODO" in entry.comment:
            num_todo[lang] += 1
        else:
            strings_to_langs[entry.msgid][lang] = entry.msgstr
        strings_to_keys[entry.msgid][lang] = set(re.findall("{.*?}",entry.msgstr))
        lang_to_strings[lang].add(entry.msgid)
    if num_todo[lang]:
        print(f"{lang} has {num_todo[lang]} TODO entries")


for lang in locales:
    if lang != DEFAULT_LANG:
        for msgid in lang_to_strings[lang]:
            if DEFAULT_LANG in strings_to_keys[msgid] and strings_to_keys[msgid][lang] != strings_to_keys[msgid][DEFAULT_LANG]:
                print(f"{msgid} has inconstent formatting keys for {lang}: ",strings_to_keys[msgid][lang],'is different from default', strings_to_keys[msgid][DEFAULT_LANG])
                errors=True

    for msgid in strings_to_langs.keys() - lang_to_strings[lang]:
        if lang == DEFAULT_LANG:
            print("Message id", msgid, "found as ", strings_to_langs[msgid], "but missing in default", DEFAULT_LANG)
            errors = True
        elif DEFAULT_LANG in strings_to_langs[msgid]:
            copied_msg = strings_to_langs[msgid][DEFAULT_LANG]
            if lang == "haha":
                entry = polib.POEntry(msgid=msgid, msgstr="ㅋㅋ" + copied_msg)
            else:
                print("Message id", msgid, "missing in ", lang, "-> Adding it from", DEFAULT_LANG)
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
