"""D-057 DG-26 Route A：角色分開生成 → 鍵控去背 → 擺位 → 合成（純 PIL／numpy；CI 可跑）。"""
import hashlib
import json

import numpy as np
import pytest
from PIL import Image


def _person(color=(200, 40, 40), bg=(205, 205, 205), w=160, h=90, hole=True):
    """單色背景上的「人物」：矩形身體＋圓頭；身體內部有一塊與背景同色的區域（不得被挖空）。"""
    a = np.full((h, w, 3), bg, np.uint8)
    a[40:, 60:100] = color
    yy, xx = np.mgrid[:h, :w]
    a[(yy - 28) ** 2 + (xx - 80) ** 2 < 14 ** 2] = color
    if hole:
        a[60:70, 75:85] = bg
    return a


def test_key_matte_keeps_interior_same_color_region():
    from see.core.compose import key_matte

    alpha, info = key_matte(_person(), feather=0)
    assert alpha[5, 5] == 0 and alpha[50, 65] == 1.0
    assert alpha[65, 80] == 1.0  # 人物內部同背景色、但不與邊框連通 → 保留
    assert not info["matte_suspect"] and 0.03 < info["coverage"] < 0.85


def test_key_matte_flags_busy_background():
    from see.core.compose import key_matte

    rng = np.random.default_rng(0)
    busy = rng.integers(0, 255, (90, 160, 3), dtype=np.uint8)
    _, info = key_matte(busy)
    assert info["matte_suspect"] and info["warnings"]


def test_placement_parse_and_bounds():
    from see.core.compose import Placement

    assert Placement.parse("0.3") == Placement(0.3, 1.0, 0.9)
    assert Placement.parse("0.7,0.95,0.8") == Placement(0.7, 0.95, 0.8)
    for bad in ("1.2", "0.5,0,0.5", "0.5,1,0.01", "a", "1,2,3,4"):
        with pytest.raises(ValueError):
            Placement.parse(bad)


def test_composite_left_right_and_depth_order():
    from see.core.compose import Placement, composite_layers, key_matte, overlap_ratio

    bg = np.full((90, 160, 3), (20, 20, 60), np.uint8)
    red, blue = _person((220, 30, 30), hole=False), _person((30, 30, 220), hole=False)
    ra, ba = key_matte(red)[0], key_matte(blue)[0]
    out, placed = composite_layers(bg, [{"layer_id": "char_a", "rgb": red, "alpha": ra, "placement": Placement(0.3)},
                                        {"layer_id": "char_b", "rgb": blue, "alpha": ba, "placement": Placement(0.7)}],
                                   color_strength=0, shadow_opacity=0)
    ya = 70
    assert out[ya, int(0.3 * 160), 0] > 150 and out[ya, int(0.7 * 160), 2] > 150  # A 在左、B 在右
    assert out[5, 5].tolist() == [20, 20, 60]  # 背景原樣
    assert overlap_ratio(placed[0]["visible_box"], placed[1]["visible_box"]) == 0
    # 重疊時深度順序：後畫者在前
    both = composite_layers(bg, [{"layer_id": "char_a", "rgb": red, "alpha": ra, "placement": Placement(0.5)},
                                 {"layer_id": "char_b", "rgb": blue, "alpha": ba, "placement": Placement(0.5)}],
                            color_strength=0, shadow_opacity=0)[0]
    assert both[ya, 80, 2] > 150 and both[ya, 80, 0] < 100
    with pytest.raises(ValueError):
        composite_layers(bg, [{"layer_id": "x", "rgb": red, "alpha": ra, "placement": Placement(0.5, 1.5, 0.1)}])


def test_isolated_and_background_cases_reuse_ab_characters():
    from see.core.style_tests import get_case

    ab = get_case("two_characters_ab")
    for c in ab.characters:
        iso = get_case(f"ab_{c.character_id}_isolated")
        assert [x.character_id for x in iso.characters] == [c.character_id]
        assert iso.characters[0].anchor == c.anchor and iso.characters[0].position == "in the center"
        assert iso.definition_version == 2 and iso.stem_id == f"{iso.case_id}-v2"
        assert "plain light grey background" in iso.base_prompt_en and "solo" in iso.base_prompt_en
    bg = get_case("ab_background")
    assert not bg.characters and "no people" in bg.base_prompt_en


def _write_layer(d, stem, arr, valid=True, case_id="x", refs=None, char=None, version=2):
    Image.fromarray(arr).save(d / f"{stem}.png")
    ev = {"case_id": case_id, "seed": 1234, "checkpoint": {"checkpoint_id": "cyberrealistic_final"}, "technical_valid": valid,
          "generation": {"identity": {"references": refs or []}}, "case_definition_version": version,
          **({"case_characters": [{"character_id": char, "position": "in the center"}]} if char else {})}
    (d / f"{stem}.json").write_text(json.dumps(ev), encoding="utf-8")


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_compose_scene_cli_layers_provenance_and_redo_one_layer(tmp_path, monkeypatch):
    from see.app.cli import main

    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path / "ws"))
    d = tmp_path / "ws" / "style_tests"
    d.mkdir(parents=True)
    _write_layer(d, "bg", np.full((90, 160, 3), (20, 20, 60), np.uint8), case_id="ab_background")
    _write_layer(d, "a1", _person((220, 30, 30)), case_id="ab_char_a_isolated", char="char_a",
                 refs=[{"character_id": "char_a", "sha256": "a" * 64, "source": "reference_library", "library_category": "people"}])
    _write_layer(d, "a2", _person((230, 90, 30)), case_id="ab_char_a_isolated", char="char_a")
    _write_layer(d, "b1", _person((30, 30, 220)), case_id="ab_char_b_isolated", char="char_b")
    before = {p.name: _sha(p) for p in d.iterdir()}
    base = ["compose-scene", "--background", "bg", "--layer", "char_a=a1", "--layer", "char_b=b1",
            "--place", "char_a=0.3", "--place", "char_b=0.7,1.0,0.85", "--name", "v1"]
    assert main(base) == 0
    out = tmp_path / "ws" / "compositions" / "v1"
    ev = json.loads((out / "composite.json").read_text(encoding="utf-8"))
    for f in ("composite.png", "layers/char_a_mask.png", "layers/char_a_cutout.png", "layers/char_b_mask.png", "layers/char_b_cutout.png"):
        assert (out / f).is_file()
    la, lb = ev["layers"]
    assert la["layer_id"] == "char_a" and la["source_stem"] == "a1" and la["source_case_id"] == "ab_char_a_isolated"
    assert la["identity_references"][0]["sha256"] == "a" * 64 and la["source_image_sha256"] == before["a1.png"]
    assert la["visible_box"][2] <= lb["visible_box"][2] and ev["background"]["source_image_sha256"] == before["bg.png"]
    assert ev["technical_valid"] and ev["scene_validated"] is None and ev["identity_validated"] == {"char_a": None, "char_b": None}
    assert ev["commercial_cleared"] is False and ev["generated_new_images"] is False
    assert {p.name: _sha(p) for p in d.iterdir()} == before  # 不覆蓋任何 style-test evidence
    # 只重做 A：換 A 層來源，B 層的來源與 cutout 完全不變
    assert main([*base[:4], "char_a=a2", *base[5:-1], "v2"]) == 0
    ev2 = json.loads((tmp_path / "ws" / "compositions" / "v2" / "composite.json").read_text(encoding="utf-8"))
    assert ev2["layers"][0]["source_stem"] == "a2" and ev2["layers"][1]["source_image_sha256"] == lb["source_image_sha256"]
    assert _sha(tmp_path / "ws" / "compositions" / "v2" / "layers" / "char_b_cutout.png") == _sha(out / "layers" / "char_b_cutout.png")
    # 人工審查
    assert main(["compose-review", "v1", "--scene", "fail", "--identity", "char_a=pass", "--identity", "char_b=fail",
                 "--pasted", "yes", "--note", "t"]) == 0
    ev = json.loads((out / "composite.json").read_text(encoding="utf-8"))
    assert ev["scene_validated"] is False and ev["identity_validated"] == {"char_a": True, "char_b": False} and ev["pasted_look"]
    assert main(["compose-review", "v1", "--identity", "char_z=pass"]) == 2


def test_compose_scene_rejects_invalid_inputs(tmp_path, monkeypatch, capsys):
    from see.app.cli import main

    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path / "ws"))
    d = tmp_path / "ws" / "style_tests"
    d.mkdir(parents=True)
    _write_layer(d, "bg", np.full((90, 160, 3), (20, 20, 60), np.uint8))
    _write_layer(d, "bad", _person(), valid=False, char="char_a")
    _write_layer(d, "a", _person(), char="char_a")
    _write_layer(d, "b", _person(), char="char_b")
    _write_layer(d, "old", _person(), case_id="ab_char_a_isolated", char="char_a", version=None)
    assert main(["compose-scene", "--background", "bg", "--layer", "char_a=bad", "--place", "char_a=0.3"]) == 2  # technical_valid=false
    assert main(["compose-scene", "--background", "bg", "--layer", "char_a=a"]) == 2  # 缺 --place
    assert main(["compose-scene", "--background", "bg", "--layer", "char_a=missing", "--place", "char_a=0.3"]) == 2
    assert main(["compose-scene", "--background", "bg", "--layer", "char_a=a", "--layer", "char_a=a",
                 "--place", "char_a=0.3"]) == 2  # layer_id 重複
    assert main(["compose-scene", "--background", "bg", "--layer", "char_a=a", "--place", "char_a=0.3",
                 "--order", "char_a,char_b"]) == 2
    # D-058：角色層以 character_id 綁定——把 char_b 的圖放到 char_a 層 → fail closed
    assert main(["compose-scene", "--background", "bg", "--layer", "char_a=b", "--place", "char_a=0.3"]) == 2
    assert "與 layer 的 character_id 不符" in capsys.readouterr().err
    # 舊 A／B 定義（historical_reversed_character_mapping）不可作角色層
    assert main(["compose-scene", "--background", "bg", "--layer", "char_a=old", "--place", "char_a=0.3"]) == 2
    assert "historical_reversed_character_mapping" in capsys.readouterr().err


def test_isolated_case_identity_single_reference_full_frame(tmp_path, monkeypatch):
    from see.app.cli import _identity_references
    from see.core.config import Settings
    from see.core.style_tests import get_case
    from tests.test_identity_adapters import _ws

    _ws(tmp_path, monkeypatch)
    refs, err = _identity_references(Settings(), get_case("ab_char_a_isolated"), ["char_a=ref_female"])
    assert err is None and [(r["character_id"], r["region"]) for r in refs] == [("char_a", "center")]
    refs, err = _identity_references(Settings(), get_case("ab_char_a_isolated"), ["char_a=ref_female", "char_b=ref_male"])
    assert err  # 單人層只收本角色的 reference

