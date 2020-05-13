from typing import Any, List, Tuple
import os

try:
    import importlib.resources as pkg_resources
except:
    import importlib_resources as pkg_resources

OUTPUT_ERROR = -1
OUTPUT_KATAGO_STDERR = -0.5
OUTPUT_INFO = 0
OUTPUT_DEBUG = 1
OUTPUT_EXTRA_DEBUG = 2


def var_to_grid(array_var: List[Any], size: Tuple[int, int]) -> List[List[Any]]:
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


resource_scopes = []


def clean_temp():
    for s in resource_scopes:
        s.__exit__(None, None, None)


def find_package_resource(path):
    if path.startswith("katrain"):
        parts = path.replace("\\", "/").split("/")
        try:
            path_obj = pkg_resources.path(".".join(parts[:-1]), parts[-1]).__enter__()
            resource_scopes.append(path_obj)
            return str(path_obj)
        except (ModuleNotFoundError, FileNotFoundError) as e:
            print(f"File {path} not found, installation possibly broken")
            return f"FILENOTFOUND::{path}"
    else:
        return path  # absolute path
