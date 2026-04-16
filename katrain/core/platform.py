from __future__ import annotations

import sys


def detect_platform() -> str:
    if sys.platform.startswith("win"):
        return "win"
    if sys.platform == "darwin":
        return "macosx"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


APP_PLATFORM = detect_platform()
