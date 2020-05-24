import os
import polib
from collections import defaultdict

localedir = "katrain/i18n/locales"
locales = set(os.listdir(localedir))
print("locales found:",locales)

strings_to_langs = defaultdict(dict)
lang_to_strings = defaultdict(set)

DEFAULT_LANG = "en"

po = {}
for lang in locales:
    pofile = os.path.join(localedir, lang, 'LC_MESSAGES', 'katrain.po')
    po[lang] = polib.pofile(pofile)
    for entry in po[lang].translated_entries():
        if 'TODO' in  entry.comment:
            print(lang,'/',entry.msgid,'is TODO')
        else:
            strings_to_langs[entry.msgid][lang] = entry.msgstr
        lang_to_strings[lang].add(entry.msgid)


for lang in locales:
    for msgid in strings_to_langs.keys() - lang_to_strings[lang]:
        if lang==DEFAULT_LANG:
            print("Message id",msgid,"found as ",strings_to_langs[msgid],"but missing in default",DEFAULT_LANG)
        elif DEFAULT_LANG in strings_to_langs[msgid]:
            print("Message id", msgid, "missing in ",lang,'-> Adding it from',DEFAULT_LANG)
            entry = polib.POEntry(msgid=msgid,msgstr=strings_to_langs[msgid][DEFAULT_LANG],comment="TODO")
            po[lang].append(entry)
        else:
            print(f"MISSING IN DEFAULT AND {lang}",strings_to_langs[msgid])
    po[lang].save(pofile)
    mofile = pofile.replace('.po', '.mo')
    po[lang].save_as_mofile(mofile)
    print('Fixed',pofile,'and converted ->',mofile)

