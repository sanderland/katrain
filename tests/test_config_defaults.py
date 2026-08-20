import json

from kivy.storage.jsonstore import JsonStore

from katrain.core.base_katrain import KaTrainBase


def test_missing_config_keys_are_seeded_from_package_defaults(tmp_path):
    """A 1.19.0-era config lacks keys added since; the settings popups turn absent
    keys into "", so they must be filled in from the package config at load time."""
    pkg = json.load(open("katrain/config.json"))
    user = json.loads(json.dumps(pkg))
    del user["general"]["anim_pv_moves"]
    del user["trainer"]["show_move_numbers"]
    user_file = tmp_path / "config.json"
    user_file.write_text(json.dumps(user))

    k = KaTrainBase.__new__(KaTrainBase)
    k.log = lambda *a, **kw: None

    k._config = dict(JsonStore(str(user_file)))
    assert "anim_pv_moves" not in k._config["general"]
    k._add_missing_config_defaults("katrain/config.json", str(user_file))
    assert k._config["general"]["anim_pv_moves"] == pkg["general"]["anim_pv_moves"]
    assert k._config["trainer"]["show_move_numbers"] == pkg["trainer"]["show_move_numbers"]
