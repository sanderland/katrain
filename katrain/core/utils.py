import os
import struct
import sys
from typing import List, Tuple, TypeVar

try:
    import importlib.resources as pkg_resources
except ImportError:
    import importlib_resources as pkg_resources

T = TypeVar("T")


def var_to_grid(array_var: List[T], size: Tuple[int, int]) -> List[List[T]]:
    """convert ownership/policy to grid format such that grid[y][x] is for move with coords x,y"""
    ix = 0
    grid = [[]] * size[1]
    for y in range(size[1] - 1, -1, -1):
        grid[y] = array_var[ix : ix + size[0]]
        ix += size[0]
    return grid


def evaluation_class(points_lost: float, eval_thresholds: List[float]):
    i = 0
    while i < len(eval_thresholds) - 1 and points_lost < eval_thresholds[i]:
        i += 1
    return i


def check_thread(tb=False):  # for checking if draws occur in correct thread
    import threading

    print("build in ", threading.current_thread().ident)
    if tb:
        import traceback

        traceback.print_stack()


PATHS = {}


def find_package_resource(path, silent_errors=False):
    global PATHS
    if path.startswith("katrain"):
        if not PATHS.get("PACKAGE"):
            try:
                with pkg_resources.path("katrain", "gui.kv") as p:
                    PATHS["PACKAGE"] = os.path.split(str(p))[0]
            except (ModuleNotFoundError, FileNotFoundError, ValueError) as e:
                print(f"Package path not found, installation possibly broken. Error: {e}", file=sys.stderr)
                return f"FILENOTFOUND/{path}"
        return os.path.join(PATHS["PACKAGE"], path.replace("katrain\\", "katrain/").replace("katrain/", ""))
    else:
        return os.path.abspath(os.path.expanduser(path))  # absolute path


def pack_floats(float_list):
    if float_list is None:
        return b""
    return struct.pack(f"{len(float_list)}e", *float_list)


def unpack_floats(str, num):
    if not str:
        return None
    return struct.unpack(f"{num}e", str)


def format_visits(n):
    if n < 1000:
        return str(n)
    if n < 1e5:
        return f"{n/1000:.1f}k"
    if n < 1e6:
        return f"{n/1000:.0f}k"
    return f"{n/1e6:.0f}k"


def json_truncate_arrays(data, lim=20):
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            return [json_truncate_arrays(d) for d in data]
        if len(data) > lim:
            data = [f"{len(data)} x {type(data[0]).__name__}"]
        return data
    elif isinstance(data, dict):
        return {k: json_truncate_arrays(v) for k, v in data.items()}
    else:
        return data
