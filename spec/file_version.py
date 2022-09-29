# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.win32 import versioninfo as ver
import importlib
import os
import pathlib
import sys

# only create VSVersionInfo object on Windows
versionInfo = None

if os.name == 'nt':

    # load constants.py to get version number and program name
    constantsPath = pathlib.Path(__file__).parent.parent.joinpath('katrain/core/constants.py').resolve()
    constSpec = importlib.util.spec_from_file_location('constants', constantsPath)
    constModule = importlib.util.module_from_spec(constSpec)
    sys.modules['constants'] = constModule
    constSpec.loader.exec_module(constModule)

    # build VSVersionInfo compatible version numbers
    verParts = constModule.VERSION.split('.')
    numParts = len(verParts)
    verList = list()
    verString = ''

    for i in range(4):
        if i <= numParts - 1:
            verList.append(int(verParts[i]))
            verString = verString + verParts[i] + '.'
        else:
            verList.append(int(0))
            verString = verString + '0.'

    verString = verString.rstrip('.')
    verTuple = tuple(verList)

    versionInfo = ver.VSVersionInfo(
        ffi=ver.FixedFileInfo(
            filevers=verTuple,  # must be 4 item tuple
            prodvers=verTuple,  # must be 4 item tuple
            mask=0x3f,          # Contains a bitmask that specifies the valid bits 'flags'r
            flags=0x0,          # Contains a bitmask that specifies the Boolean attributes of the file.
            OS=0x40004,         # The operating system for which this file was designed. 0x4 - NT and there is no need to change it.
            fileType=0x1,       # The general type of file. 0x1 - the file is an application.
            subtype=0x0,        # The function of the file. 0x0 - the function is not defined for this fileType
            date=(0, 0)         # Creation date and time stamp.
        ),
        kids=[
            ver.StringFileInfo([
                ver.StringTable(
                    '040904B0',
                    [ver.StringStruct('FileDescription', constModule.PROGRAM_NAME),
                    ver.StringStruct('FileVersion', verString),
                    ver.StringStruct('LegalCopyright', constModule.HOMEPAGE),
                    ver.StringStruct('OriginalFilename', constModule.PROGRAM_NAME + '.exe'),
                    ver.StringStruct('ProductName', constModule.PROGRAM_NAME),
                    ver.StringStruct('ProductVersion', verString)]
                )
            ]),
            ver.VarFileInfo(
                [ver.VarStruct('Translation', [1033, 1200])]
            )
        ]
    )
