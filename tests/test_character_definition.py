"""D-058：Character Definition／Reference Asset schema 與 Character Validation Gate。"""
import json

import pytest
from pydantic import ValidationError

from see.models.character_definition import (CharacterDefinition, CharacterType, CommercialClearance, Depth, GenderPresentation,
                                             Horizontal, RefCategory, ReferenceAsset, RefRole, ScenePlacement, SourceType,
                                             VoiceAssignment, blocking, support_status, validate_characters)

SHA_A, SHA_B = "a" * 64, "b" * 64


def _asset(aid, cid, sha, role=RefRole.identity_face, cat=RefCategory.people, path="/home/u/ws/ref.png", **kw):
    return ReferenceAsset(asset_id=aid, category=cat, file_path=path, character_id=cid, role=role, sha256=sha,
                          source_type=SourceType.user_supplied, **kw)


def _two():
    return [CharacterDefinition(character_id="char_001", display_name="男主角", gender_presentation=GenderPresentation.male),
            CharacterDefinition(character_id="char_002", display_name="女主角", gender_presentation=GenderPresentation.female)]


def _places():
    return [ScenePlacement(character_id="char_001", horizontal=Horizontal.left),
            ScenePlacement(character_id="char_002", horizontal=Horizontal.right)]


def test_defaults_are_unspecified_and_nothing_is_filled_in():
    c = CharacterDefinition(character_id="char_001", display_name="x")
    assert c.gender_presentation == GenderPresentation.unspecified and c.appearance_region == ""
    assert c.character_type == CharacterType.person and c.default_style_profile is None and c.voice_profile is None
    assert c.to_appearance().anchor_text == ""  # 缺資料不補值、不輸出任何性別／族群詞
    with pytest.raises(ValidationError):
        CharacterDefinition(character_id="A", display_name="x")  # 穩定 id：小寫 slug（例 char_001）
    with pytest.raises(ValidationError):
        CharacterDefinition(character_id="char_001", display_name="x", gender_presentation="woman")  # 只收顯式 enum


def test_identity_is_separate_from_style_mood_voice():
    c = CharacterDefinition(character_id="char_001", display_name="男主角", gender_presentation=GenderPresentation.male,
                            hair_style="short", hair_color="grey", face_shape="oval", expression="calm", outfit="grey suit",
                            default_style_profile="realistic", default_mood_profile="warm",
                            voice_profile=VoiceAssignment(voice_id="zm_010", speed=1.0, emotion="calm"))
    a = c.to_appearance().anchor_text
    assert a == "man, short grey hair, oval face, calm expression, wearing grey suit"
    assert "realistic" not in a and "warm" not in a and "zm_010" not in a


def test_reference_asset_local_only_and_support_status():
    with pytest.raises(ValidationError):
        _asset("r1", "char_001", SHA_A, path="https://x/y.png")
    assert support_status(RefCategory.people, RefRole.identity_face) != "not yet supported"
    for cat in (RefCategory.animals, RefCategory.characters, RefCategory.backgrounds, RefCategory.styles):
        for role in RefRole:
            assert support_status(cat, role) == "not yet supported"


def test_gate_passes_clean_definition_with_nonblocking_clearance_warning():
    issues = validate_characters(_two(), [_asset("r1", "char_001", SHA_A), _asset("r2", "char_002", SHA_B)], _places(),
                                 require_identity_reference=True)
    assert not blocking(issues) and {i.code for i in issues} == {"commercial_clearance_unknown"}
    final = validate_characters(_two(), [_asset("r1", "char_001", SHA_A), _asset("r2", "char_002", SHA_B)], _places(),
                                final_output=True)
    assert {i.code for i in blocking(final)} == {"commercial_clearance_unknown"}  # 正式輸出時授權未知 → 擋


@pytest.mark.parametrize("mutate,code", [
    (lambda c, a, p: c.append(c[0]), "duplicate_character_id"),
    (lambda c, a, p: a.append(_asset("r3", "char_002", SHA_A)), "reference_shared_across_characters"),
    (lambda c, a, p: a.append(_asset("r3", None, "c" * 64)), "asset_unbound"),
    (lambda c, a, p: a.append(_asset("r3", "char_009", "c" * 64)), "asset_unknown_character"),
    (lambda c, a, p: a.append(_asset("r3", "char_001", "c" * 64, role=RefRole.style_reference)), "role_category_mismatch"),
    (lambda c, a, p: p.pop(), "placement_missing"),
    (lambda c, a, p: p.append(ScenePlacement(character_id="char_001", horizontal=Horizontal.center)), "placement_duplicate"),
    (lambda c, a, p: p.__setitem__(1, ScenePlacement(character_id="char_002", horizontal=Horizontal.left)), "placement_collision"),
    (lambda c, a, p: c[0].reference_asset_ids.append("r2"), "asset_owner_mismatch"),
    (lambda c, a, p: c[0].reference_asset_ids.append("nope"), "missing_asset"),
    (lambda c, a, p: a.append(_asset("r3", "char_001", "c" * 64, cat=RefCategory.animals)), "asset_type_mismatch"),
    (lambda c, a, p: a.append(_asset("r1", "char_001", "d" * 64)), "duplicate_asset_id"),
])
def test_gate_fails_closed_on_conflicts(mutate, code):
    c, a, p = _two(), [_asset("r1", "char_001", SHA_A), _asset("r2", "char_002", SHA_B)], _places()
    mutate(c, a, p)
    assert code in {i.code for i in blocking(validate_characters(c, a, p))}


def test_gate_flags_private_image_inside_repo(tmp_path):
    repo = tmp_path / "repo"
    issues = validate_characters(_two(), [_asset("r1", "char_001", SHA_A, path=str(repo / "docs" / "me.jpg")),
                                          _asset("r2", "char_002", SHA_B, path=str(repo / "workspace" / "ok.jpg"))],
                                 _places(), repo_root=repo)
    assert [i.code for i in blocking(issues)] == ["private_image_in_repo"]


def test_placement_and_depth_are_explicit_fields_not_from_id():
    p = ScenePlacement(character_id="char_a", horizontal=Horizontal.right, depth=Depth.foreground, shot_size="medium shot")
    assert p.horizontal == Horizontal.right  # char_a 不隱含 left


# ---------------------------------------------------------------- CLI 整合：sidecar metadata 與 gate
def test_style_test_ref_sidecar_metadata_must_match_binding(tmp_path, monkeypatch):
    from PIL import Image

    from see.app.cli import _identity_references
    from see.core.config import Settings
    from see.core.hashing import file_sha256
    from see.core.style_tests import get_case
    from tests.test_identity_adapters import _ws

    _ws(tmp_path, monkeypatch)
    lib = tmp_path / "ws" / "reference_library" / "people"
    lib.mkdir(parents=True)
    img = lib / "hero_male_v1.jpg"
    Image.new("RGB", (32, 32), (1, 2, 3)).save(img)
    meta = {"asset_id": "hero_male_v1", "category": "people", "file_path": str(img), "character_id": "char_b",
            "role": "identity_face", "sha256": file_sha256(img), "source_type": "user_supplied"}
    side = img.with_name(img.name + ".ref.json")
    side.write_text(json.dumps(meta), encoding="utf-8")
    case = get_case("two_characters_ab")
    _, err = _identity_references(Settings(), case, ["char_a=people/hero_male_v1.jpg", "char_b=ref_male"])
    assert err and "metadata 衝突" in err  # metadata 說這張是 char_b，卻被指給 char_a → 不生成
    side.write_text(json.dumps({**meta, "character_id": "char_a"}), encoding="utf-8")
    refs, err = _identity_references(Settings(), case, ["char_a=people/hero_male_v1.jpg", "char_b=ref_male"])
    assert err is None and refs[0]["asset_metadata"]["asset_id"] == "hero_male_v1"
    side.write_text(json.dumps({**meta, "character_id": "char_a", "role": "outfit"}), encoding="utf-8")
    _, err = _identity_references(Settings(), case, ["char_a=people/hero_male_v1.jpg", "char_b=ref_male"])
    assert err and "identity_face" in err
    side.write_text(json.dumps({**meta, "character_id": "char_a", "sha256": "0" * 64}), encoding="utf-8")
    _, err = _identity_references(Settings(), case, ["char_a=people/hero_male_v1.jpg", "char_b=ref_male"])
    assert err and "sha256" in err


def test_historical_reversed_flag():
    from see.core.style_tests import historical_reversed_character_mapping as h

    assert h({"case_id": "two_characters_ab"}) and h({"case_id": "ab_char_a_isolated", "case_definition_version": 1})
    assert not h({"case_id": "two_characters_ab", "case_definition_version": 2})
    assert not h({"case_id": "ab_background"}) and not h({"case_id": "east_asian_male_portrait"})
