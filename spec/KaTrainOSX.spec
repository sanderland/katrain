# -*- mode: python ; coding: utf-8 -*-
from kivy.tools.packaging.pyinstaller_hooks import get_deps_all, hookspath, runtime_hooks
from kivymd import hooks_path as kivymd_hooks_path
import subprocess

block_cipher = None

# pyinstaller spec/KaTrain.spec --noconfirm
# --upx-dir my


a = Analysis(
    ["../katrain/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("../katrain/gui.kv", "katrain"),
        ("../katrain/popups.kv", "katrain"),
        ("../katrain/config.json", "katrain"),
        ("../katrain/KataGo", "katrain/KataGo"),
        ("../katrain/models", "katrain/models"),
        ("../katrain/sounds", "katrain/sounds"),
        ("../katrain/img", "katrain/img"),
        ("../katrain/fonts", "katrain/fonts"),
        ("../katrain/i18n", "katrain/i18n"),
    ],
    hiddenimports=["win32file", "win32timezone"],  #  FileChooser in kivy loads this conditionally
    hookspath=[kivymd_hooks_path],
    excludes=["scipy", "pandas", "numpy", "matplotlib", "docutils", "mkl"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

EXCLUDE_SUFFIX = ["katago", "katago.exe"]
EXCLUDE = ["KataGoData", "anim_", "screenshot_", "__pycache__"]
a.datas = [
    (ff, ft, tp)
    for ff, ft, tp in a.datas
    if not any(ff.endswith(suffix) for suffix in EXCLUDE_SUFFIX) and not any(kw in ff for kw in EXCLUDE)
]

console = False
name = "KaTrain"

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name=name,
    debug=False,
    strip=False,
    upx=False,
    console=console,
)

coll = COLLECT(
    exe, #                Tree('/Library/Frameworks/SDL2_ttf.framework/Versions/A/Frameworks/FreeType.framework'),
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=name,
)

app = BUNDLE(coll, name="KaTrain.app", icon="../katrain/img/icon.ico", bundle_identifier=None)
