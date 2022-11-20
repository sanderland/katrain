# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.win32 import versioninfo as ver
import os

# only create VSVersionInfo object on Windows
versionInfo = None

if os.name == "nt":

    # load constants.py to get version number and program name
    import katrain.core.constants as constants

    # build VSVersionInfo compatible version numbers
    verParts = constants.VERSION.split(".")
    numParts = len(verParts)
    verList = list()
    verString = ""

    for i in range(4):
        if i <= numParts - 1:
            verList.append(int(verParts[i]))
            verString = verString + verParts[i] + "."
        else:
            verList.append(int(0))
            verString = verString + "0."

    verString = verString.rstrip(".")
    verTuple = tuple(verList)

    versionInfo = ver.VSVersionInfo(
        ffi=ver.FixedFileInfo(
            filevers=verTuple,  # must be 4 item tuple
            prodvers=verTuple,  # must be 4 item tuple
            mask=0x3F,  # Contains a bitmask that specifies the valid bits 'flags'r
            flags=0x0,  # Contains a bitmask that specifies the Boolean attributes of the file.
            OS=0x40004,  # The operating system for which this file was designed. 0x4 - NT and there is no need to change it.
            fileType=0x1,  # The general type of file. 0x1 - the file is an application.
            subtype=0x0,  # The function of the file. 0x0 - the function is not defined for this fileType
            date=(0, 0),  # Creation date and time stamp.
        ),
        kids=[
            ver.StringFileInfo(
                [
                    ver.StringTable(
                        "040904B0",
                        [
                            ver.StringStruct("FileDescription", constants.PROGRAM_NAME),
                            ver.StringStruct("FileVersion", verString),
                            ver.StringStruct("LegalCopyright", constants.HOMEPAGE),
                            ver.StringStruct("OriginalFilename", constants.PROGRAM_NAME + ".exe"),
                            ver.StringStruct("ProductName", constants.PROGRAM_NAME),
                            ver.StringStruct("ProductVersion", verString),
                        ],
                    )
                ]
            ),
            ver.VarFileInfo([ver.VarStruct("Translation", [1033, 1200])]),
        ],
    )
