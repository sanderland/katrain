import copy
import glob
import os
import re
import sys
from collections import defaultdict

import polib

localedir = "katrain/i18n/locales"
locales = set(os.listdir(localedir))
print("locales found:", locales)

strings_to_langs = defaultdict(dict)
strings_to_keys = defaultdict(dict)
lang_to_strings = defaultdict(set)

DEFAULT_LANG = "en"
INACTIVE_LANGS = ["es"]
errors = False

po = {}
pofile = {}
todos = defaultdict(list)

for lang in locales:
    if lang in INACTIVE_LANGS:
        continue
    pofile[lang] = os.path.join(localedir, lang, "LC_MESSAGES", "katrain.po")
    po[lang] = polib.pofile(pofile[lang])
    for entry in po[lang].translated_entries():
        if "TODO" in entry.comment and "DEPRECATED" not in entry.comment:
            todos[lang].append(entry)
        strings_to_langs[entry.msgid][lang] = entry
        strings_to_keys[entry.msgid][lang] = set(re.findall("{.*?}", entry.msgstr))
        if entry.msgid in lang_to_strings[lang]:
            print("duplicate", entry.msgid, "in", lang, "--> deleting", entry.msgstr)
            errors = True
            po[lang].remove(entry)
        else:
            lang_to_strings[lang].add(entry.msgid)
    if todos[lang] and any("todo" in a for a in sys.argv):
        print(f"========== {lang} has {len(todos[lang])} TODO entries ========== ")
        for item in todos[lang]:
            print(item)


for lang in locales:
    if lang in INACTIVE_LANGS:
        continue
    if lang != DEFAULT_LANG:
        for msgid in lang_to_strings[lang]:
            if (
                DEFAULT_LANG in strings_to_keys[msgid]
                and strings_to_keys[msgid][lang] != strings_to_keys[msgid][DEFAULT_LANG]
            ):
                print(
                    f"{msgid} has inconstent formatting keys for {lang}: ",
                    strings_to_keys[msgid][lang],
                    "is different from default",
                    strings_to_keys[msgid][DEFAULT_LANG],
                )
                errors = True

    for msgid in strings_to_langs.keys() - lang_to_strings[lang]:
        if lang == DEFAULT_LANG:
            print("Message id", msgid, "found as ", strings_to_langs[msgid], "but missing in default", DEFAULT_LANG)
            errors = True
        elif DEFAULT_LANG in strings_to_langs[msgid]:
            copied_entry = copy.copy(strings_to_langs[msgid][DEFAULT_LANG])
            print("Message id", msgid, "missing in ", lang, "-> Adding it from", DEFAULT_LANG)
            if copied_entry.comment:
                copied_entry.comment = f"TODO - {copied_entry.comment}"
            else:
                copied_entry.comment = "TODO"
            po[lang].append(copied_entry)
            errors = True
        else:
            print(f"MISSING IN DEFAULT AND {lang}", msgid)
            errors = True

    for msgid, lang_entries in strings_to_langs.items():
        if lang in lang_entries and "TODO" in lang_entries[lang].comment:
            if any(e.msgstr == lang_entries[lang].msgstr for ll, e in lang_entries.items() if ll != lang):
                if lang_entries.get(DEFAULT_LANG):
                    todo_comment = (
                        f"TODO - {lang_entries[DEFAULT_LANG].comment}" if lang_entries[DEFAULT_LANG].comment else "TODO"
                    )  # update todo
                    if (
                        lang_entries[lang].msgstr != lang_entries[DEFAULT_LANG].msgstr
                        or lang_entries[lang].comment.replace("\n", " ") != todo_comment
                    ):
                        print(
                            [
                                lang_entries[lang].msgstr,
                                lang_entries[DEFAULT_LANG].msgstr,
                                lang_entries[lang].comment,
                                todo_comment,
                            ]
                        )
                        lang_entries[lang].msgstr = lang_entries[DEFAULT_LANG].msgstr  # update
                        lang_entries[lang].comment = todo_comment
                        print(f"{lang}/{msgid} todo entry updated")

    po[lang].save(pofile[lang])
    mofile = pofile[lang].replace(".po", ".mo")
    po[lang].save_as_mofile(mofile)
    print("Fixed", pofile[lang], "and converted ->", mofile)


for ext in ["py", "kv"]:
    lc = 0
    for file in glob.glob(f"katrain/*.{ext}") + glob.glob(f"katrain/**/*.{ext}"):
        with open(file, "r") as f:
            for i, line in enumerate(f.readlines()):
                if line.strip():
                    lc += 1
                matches = [m.strip() for m in re.findall(r"i18n._\((.*?)\)", line)]
                for msgid in matches:
                    stripped_msgid = msgid.strip("\"'")
                    if stripped_msgid and msgid[0] in ['"', "'"] and stripped_msgid not in strings_to_langs:  # not code
                        print(f"Missing {msgid} used in code at \t{file}:{i} \t'{line.strip()}'")
                        errors += 1
    print(f"Checked {lc} lines of {ext} code for missing i18n entries.")
sys.exit(int(errors))
