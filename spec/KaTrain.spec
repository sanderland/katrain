# -*- mode: python ; coding: utf-8 -*-
from kivy_deps import sdl2, glew
from kivymd import hooks_path as kivymd_hooks_path

block_cipher = None
console = True

# pyinstaller spec/katrain.spec --noconfirm
# --upx-dir my

a = Analysis(
    ["..\\katrain\\__main__.py"],
    pathex=["C:\\Users\\sande\\Desktop\\katrain\\spec"],
    binaries=[],
    datas=[
        ("..\\katrain\\gui.kv", "katrain"),
        ("..\\katrain\\popups.kv", "katrain"),
        ("..\\katrain\\config.json", "katrain"),
        ("..\\katrain\\KataGo", "katrain\\KataGo"),
        ("..\\katrain\img", "katrain\\img"),
        ("..\\katrain\\models", "katrain\\models"),
        ("..\\katrain\\i18n", "katrain\\i18n"),
        ("..\\katrain\\fonts", "katrain\\fonts"),
    ],
    hiddenimports=["win32file", "win32timezone"],  #  FileChooser in kivy loads this conditionally
    hookspath=[kivymd_hooks_path],
    excludes=["scipy", "pandas", "numpy", "matplotlib", "docutils", "mkl"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

print("SCRIPTS", len(a.scripts), "BIN", len(a.binaries), "ZIP", len(a.zipfiles), "DATA", len(a.datas))

EXCLUDE_SUFFIX = ["katago"]
EXCLUDE = ["KataGoData", "anim_", "screenshot_", "__pycache__", "locales/haha"]
a.datas = [
    (ff, ft, tp)
    for ff, ft, tp in a.datas
    if not any(ff.endswith(suffix) for suffix in EXCLUDE_SUFFIX) and not any(kw in ff for kw in EXCLUDE)
]

print("DATA FILTERED", len(a.datas))

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KaTrain",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=console,
    icon="C:\\icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)],
    strip=False,
    upx=True,
    upx_exclude=[],
    name="KaTrain",
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)],
    debug=False,
    strip=False,
    upx=True,
    name="KaTrain",
    console=console,
    icon="C:\\icon.ico",
)
