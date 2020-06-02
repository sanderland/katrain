import os
import sys
from typing import List, Tuple, TypeVar

try:
    import importlib.resources as pkg_resources
except:
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


def find_package_resource(path, silent_errors=False):
    if path.startswith("katrain"):
        parts = path.replace("\\", "/").split("/")
        try:
            with pkg_resources.path(".".join(parts[:-1]), parts[-1]) as path_obj:
                return str(path_obj)  # this will clean up if egg etc, but these don't work anyway
        except (ModuleNotFoundError, FileNotFoundError, ValueError) as e:
            if silent_errors:
                return None
            print(f"File {path} not found, installation possibly broken", file=sys.stderr)
            return f"FILENOTFOUND::{path}"
    else:
        return os.path.abspath(os.path.expanduser(path))  # absolute path
