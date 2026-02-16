from katrain.gui.components.forms import FieldSpec, FormModel


def test_form_model_load_defaults_and_apply():
    model = FormModel()
    model.add(FieldSpec(key="engine/max_visits", label_key="engine:max_visits", default=123, parser=int))
    model.add(FieldSpec(key="general/anim_pv_time", label_key="general:anim_pv_time", default=0.5, parser=float))

    cfg = {"engine": {}, "general": {}}
    model.load_from_config(cfg)
    assert model.get("engine/max_visits") == 123
    assert model.get("general/anim_pv_time") == 0.5

    model.set("engine/max_visits", "250")
    model.set("general/anim_pv_time", "0.75")
    model.apply_to_config(cfg)

    assert cfg["engine"]["max_visits"] == 250
    assert cfg["general"]["anim_pv_time"] == 0.75


def test_form_model_duplicate_field_key_raises():
    model = FormModel()
    model.add(FieldSpec(key="engine/model", label_key="engine:model", default="a.bin.gz"))
    try:
        model.add(FieldSpec(key="engine/model", label_key="engine:model", default="b.bin.gz"))
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError on duplicate field key")

