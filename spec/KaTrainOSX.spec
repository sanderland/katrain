# -*- mode: python ; coding: utf-8 -*-
from kivy.tools.packaging.pyinstaller_hooks import get_deps_all, hookspath, runtime_hooks
from kivymd import hooks_path as kivymd_hooks_path

block_cipher = None

# pyinstaller spec/KaTrain.spec --noconfirmf
# --upx-dir my


a = Analysis(
    ["../katrain/__main__.py"],
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

xargs = []
import platform

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    *xargs,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=name,
)

app = BUNDLE(coll, name="KaTrain.app", icon="../katrain/img/icon.ico", bundle_identifier=None)
