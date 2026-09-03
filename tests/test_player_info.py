import ast
from pathlib import Path


def test_player_info_refreshes_its_label_after_kv_build():
    panels = Path("katrain/gui/widgets/panels.py")
    module = ast.parse(panels.read_text())

    player_info = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "PlayerInfo")
    on_kv_post = next(
        node for node in player_info.body if isinstance(node, ast.FunctionDef) and node.name == "on_kv_post"
    )

    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        and node.func.attr == "set_label"
        for node in ast.walk(on_kv_post)
    )
