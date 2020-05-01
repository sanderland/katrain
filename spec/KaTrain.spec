# -*- mode: python ; coding: utf-8 -*-
from kivy_deps import sdl2, glew

block_cipher = None

# build with  "pyinstaller spec/katrain.spec --noconfirm"

a = Analysis(['..\\katrain.py'],
             pathex=['C:\\Users\\sande\\Desktop\\katrain\\spec'],
             binaries=[],
             datas=[('..\\katrain.kv','.'),('..\\config.json','.'),('..\\KataGo','KataGo'),('..\\img','img')],
             hiddenimports=["win32file","win32timezone"], #  FileChooser in kivy loads this conditionally
             hookspath=[],
             runtime_hooks=[],
             excludes=['..\\bots'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

print("SCRIPTS",a.scripts)

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='KaTrain',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True) #  , icon='..\\icon.png'
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)],
               strip=False,
               upx=True,
               upx_exclude=[],
               name='KaTrain')
