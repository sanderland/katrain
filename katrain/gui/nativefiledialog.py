"""Native OS file open/save dialogs.

Uses osascript (macOS), the comdlg32 API via ctypes (Windows) or
zenity/kdialog (Linux) to show the platform's own file dialog instead of
the in-app Kivy FileBrowser. Dialogs run in a background thread so the
Kivy event loop keeps running; the result (a path, or None on cancel) is
delivered to the callback on the Kivy main thread. If the dialog fails to
show, error_callback is called instead, so callers can fall back to the
Kivy FileBrowser popup. Callers should check available() first and use
the popup directly when it returns False.
"""

import os
import shutil
import subprocess
import threading

from kivy.clock import Clock
from kivy.logger import Logger
from kivy.utils import platform as kivy_platform

_dialog_lock = threading.Lock()
_dialog_open = False


def available() -> bool:
    if kivy_platform in ("macosx", "win"):
        return True
    if kivy_platform == "linux":
        return shutil.which("zenity") is not None or shutil.which("kdialog") is not None
    return False


def open_file(callback, error_callback=None, prompt="", initial_dir=None, extensions=None):
    """Show a native 'open file' dialog, then call callback(path_or_None) on the main thread."""
    initial_dir = _existing_dir(initial_dir)
    _launch(callback, error_callback, lambda: _open_impl(prompt, initial_dir, extensions or []))


def save_file(callback, error_callback=None, prompt="", initial_dir=None, suggested_name="", extensions=None):
    """Show a native 'save file' dialog, then call callback(path_or_None) on the main thread."""
    initial_dir = _existing_dir(initial_dir)
    _launch(callback, error_callback, lambda: _save_impl(prompt, initial_dir, suggested_name, extensions or []))


class DialogError(Exception):
    pass


def _existing_dir(path):
    if path:
        path = os.path.abspath(os.path.expanduser(path))
        while path and not os.path.isdir(path):
            parent = os.path.dirname(path)
            if parent == path:
                break
            path = parent
    return path if path and os.path.isdir(path) else os.path.expanduser("~")


def _launch(callback, error_callback, dialog_fn):
    global _dialog_open
    with _dialog_lock:
        if _dialog_open:  # a dialog is already showing, ignore repeated requests
            return
        _dialog_open = True

    def worker():
        global _dialog_open
        result, failed = None, False
        try:
            result = dialog_fn()
        except Exception as e:
            Logger.warning(f"nativefiledialog: dialog failed: {e}")
            failed = True
        finally:
            with _dialog_lock:
                _dialog_open = False
        if failed and error_callback:
            Clock.schedule_once(lambda _dt: error_callback())
        else:
            Clock.schedule_once(lambda _dt: callback(result))

    threading.Thread(target=worker, daemon=True).start()


def _open_impl(prompt, initial_dir, extensions):
    if kivy_platform == "macosx":
        return _macos_dialog(f"choose file with prompt {_as_quote(prompt)}", initial_dir)
    if kivy_platform == "win":
        return _win_dialog(False, prompt, initial_dir, "", extensions)
    return _linux_dialog(False, prompt, initial_dir, "", extensions)


def _save_impl(prompt, initial_dir, suggested_name, extensions):
    if kivy_platform == "macosx":
        script = f"choose file name with prompt {_as_quote(prompt)}"
        if suggested_name:
            script += f" default name {_as_quote(suggested_name)}"
        return _macos_dialog(script, initial_dir)
    if kivy_platform == "win":
        return _win_dialog(True, prompt, initial_dir, suggested_name, extensions)
    return _linux_dialog(True, prompt, initial_dir, suggested_name, extensions)


# -- macOS ---------------------------------------------------------------


def _as_quote(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _macos_dialog(choose_script, initial_dir):
    # no 'of type' filter: extensions like .sgf have no registered UTI, which would gray out all files
    if initial_dir:
        choose_script += f" default location POSIX file {_as_quote(initial_dir)}"
    result = subprocess.run(["osascript", "-e", f"POSIX path of ({choose_script})"], capture_output=True, text=True)
    if result.returncode != 0:
        if "-128" in result.stderr:  # User canceled
            return None
        raise DialogError(result.stderr.strip() or f"osascript exited {result.returncode}")
    return result.stdout.strip() or None


# -- Windows -------------------------------------------------------------


def _win_dialog(save, prompt, initial_dir, suggested_name, extensions):
    import ctypes
    import ctypes.wintypes as w

    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", w.DWORD),
            ("hwndOwner", w.HWND),
            ("hInstance", w.HINSTANCE),
            ("lpstrFilter", w.LPCWSTR),
            ("lpstrCustomFilter", w.LPWSTR),
            ("nMaxCustFilter", w.DWORD),
            ("nFilterIndex", w.DWORD),
            ("lpstrFile", w.LPWSTR),
            ("nMaxFile", w.DWORD),
            ("lpstrFileTitle", w.LPWSTR),
            ("nMaxFileTitle", w.DWORD),
            ("lpstrInitialDir", w.LPCWSTR),
            ("lpstrTitle", w.LPCWSTR),
            ("Flags", w.DWORD),
            ("nFileOffset", w.WORD),
            ("nFileExtension", w.WORD),
            ("lpstrDefExt", w.LPCWSTR),
            ("lCustData", w.LPARAM),
            ("lpfnHook", ctypes.c_void_p),
            ("lpTemplateName", w.LPCWSTR),
            ("pvReserved", ctypes.c_void_p),
            ("dwReserved", w.DWORD),
            ("FlagsEx", w.DWORD),
        ]

    OFN_EXPLORER = 0x00080000
    OFN_PATHMUSTEXIST = 0x00000800
    OFN_FILEMUSTEXIST = 0x00001000
    OFN_HIDEREADONLY = 0x00000004
    OFN_NOCHANGEDIR = 0x00000008  # keep cwd stable, engine/model paths are relative to it
    OFN_OVERWRITEPROMPT = 0x00000002

    if extensions:
        patterns = ";".join(f"*.{e}" for e in extensions)
        filters = f"Supported files ({patterns})\0{patterns}\0All files (*.*)\0*.*\0"
    else:
        filters = "All files (*.*)\0*.*\0"

    file_buffer = ctypes.create_unicode_buffer(suggested_name, 65536)
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.lpstrFilter = filters
    ofn.lpstrFile = ctypes.cast(file_buffer, w.LPWSTR)
    ofn.nMaxFile = 65536
    ofn.lpstrInitialDir = initial_dir or None
    ofn.lpstrTitle = prompt or None
    ofn.Flags = OFN_EXPLORER | OFN_PATHMUSTEXIST | OFN_HIDEREADONLY | OFN_NOCHANGEDIR
    if save:
        ofn.Flags |= OFN_OVERWRITEPROMPT
        ofn.lpstrDefExt = extensions[0] if extensions else None
    else:
        ofn.Flags |= OFN_FILEMUSTEXIST

    dialog = ctypes.windll.comdlg32.GetSaveFileNameW if save else ctypes.windll.comdlg32.GetOpenFileNameW
    if not dialog(ctypes.byref(ofn)):
        error = ctypes.windll.comdlg32.CommDlgExtendedError()
        if error:
            raise DialogError(f"comdlg32 dialog failed with error 0x{error:x}")
        return None  # user canceled
    return file_buffer.value or None


# -- Linux ---------------------------------------------------------------


def _linux_dialog(save, prompt, initial_dir, suggested_name, extensions):
    if shutil.which("zenity"):
        cmd = ["zenity", "--file-selection", f"--title={prompt}"]
        if save:
            cmd.append("--save")
            if initial_dir or suggested_name:
                cmd.append(f"--filename={os.path.join(initial_dir or '', suggested_name)}")
        elif initial_dir:
            cmd.append(f"--filename={initial_dir.rstrip(os.sep)}{os.sep}")
        if extensions:
            cmd.append("--file-filter=" + " ".join(f"*.{e}" for e in extensions))
            cmd.append("--file-filter=*")
        cancel_codes = (1,)
    elif shutil.which("kdialog"):
        cmd = ["kdialog", "--title", prompt, "--getsavefilename" if save else "--getopenfilename"]
        cmd.append(os.path.join(initial_dir or os.path.expanduser("~"), suggested_name if save else ""))
        if extensions:
            cmd.append(" ".join(f"*.{e}" for e in extensions) + "|Supported files")
        cancel_codes = (1,)
    else:
        raise DialogError("neither zenity nor kdialog found")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if result.returncode in cancel_codes:
            return None
        raise DialogError(result.stderr.strip() or f"{cmd[0]} exited {result.returncode}")
    return result.stdout.strip() or None
