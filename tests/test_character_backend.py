"""D-062 Batch C：Reference Library service、Character CRUD、Confirmation payload（fail closed）。"""
from __future__ import annotations

import json

import pytest
from PIL import Image

from see.core.reference_library import ReferenceLibrary, ReferenceLibraryError, entries_json
from see.models.character_definition import (CharacterDefinition, GenderPresentation, Horizontal, RefRole, ScenePlacement,
                                             VoiceAssignment, confirmation_payload)
from see.storage.character_store import CharacterStore, CharacterStoreError


def _img(path, color):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), color).save(path)
    return path


@pytest.fixture
def lib(tmp_path):
    _img(tmp_path / "reference_library" / "people" / "hero_v1.jpg", (10, 10, 10))
    _img(tmp_path / "reference_library" / "people" / "hero_v2.jpg", (20, 20, 20))
    _img(tmp_path / "reference_library" / "styles" / "noir.png", (30, 30, 30))
    _img(tmp_path / "identity_refs" / "people" / "old.png", (40, 40, 40))
    return ReferenceLibrary(tmp_path)


def test_register_list_and_legacy_readonly(lib, tmp_path):
    a = lib.register("people/hero_v1.jpg", asset_id="hero_v1", role=RefRole.identity_face, source_type="user_supplied",
                     character_id="char_001", provenance={"consent": "self"})
    assert len(a.sha256) == 64 and a.provenance["consent"] == "self" and "registered_at" in a.provenance
    es = {e.rel_path: e for e in lib.list()}
    assert es["people/hero_v1.jpg"].asset.asset_id == "hero_v1" and not es["people/hero_v1.jpg"].problems
    assert es["people/hero_v2.jpg"].support == "unregistered"
    assert es["people/old.png"].legacy and es["people/old.png"].asset is None
    assert es["styles/noir.png"].support == "unregistered"
    json.loads(entries_json(lib.list()))
    with pytest.raises(ReferenceLibraryError):
        lib.register("people/hero_v1.jpg", asset_id="x", role=RefRole.identity_face, source_type="user_supplied")  # 已登記
    with pytest.raises(ReferenceLibraryError):
        lib.register("people/hero_v2.jpg", asset_id="hero_v1", role=RefRole.identity_face, source_type="user_supplied")  # id 重複
    with pytest.raises(ReferenceLibraryError):
        lib.register("styles/noir.png", asset_id="noir", role=RefRole.identity_face, source_type="imported")  # role×category
    with pytest.raises(ReferenceLibraryError):
        lib.register("../secrets/x.png", asset_id="x", role=RefRole.pose, source_type="imported")
    with pytest.raises(ReferenceLibraryError):
        lib.register("people/missing.jpg", asset_id="m", role=RefRole.pose, source_type="imported")
    assert not (tmp_path / "identity_refs" / "people" / "old.png.ref.json").exists()  # legacy 不寫入
    s = lib.register("styles/noir.png", asset_id="noir", role=RefRole.style_reference, source_type="imported")
    assert s.character_id is None and lib.list(category="styles")[0].support == "not yet supported"


def test_tampered_file_is_flagged_and_blocks_writes(lib, tmp_path):
    lib.register("people/hero_v1.jpg", asset_id="hero_v1", role=RefRole.identity_face, source_type="user_supplied",
                 character_id="char_001")
    _img(tmp_path / "reference_library" / "people" / "hero_v1.jpg", (99, 0, 0))  # 檔案被換
    e = [x for x in lib.list() if x.rel_path == "people/hero_v1.jpg"][0]
    assert any("sha256 mismatch" in p for p in e.problems)
    with pytest.raises(ReferenceLibraryError):
        lib.bind("hero_v1", "char_002")
    assert lib.assets_for("char_001") == []  # 有問題的 asset 不得被當成可用 reference


def test_bind_unbind_and_primary(lib):
    for n in ("hero_v1", "hero_v2"):
        lib.register(f"people/{n}.jpg", asset_id=n, role=RefRole.identity_face, source_type="user_supplied", character_id="char_001")
    assert lib.mark_primary("hero_v1").is_primary
    lib.mark_primary("hero_v2")
    prim = {a.asset_id: a.is_primary for a in lib.assets_for("char_001")}
    assert prim == {"hero_v1": False, "hero_v2": True}  # 同角色只有一張 primary
    un = lib.bind("hero_v2", None)
    assert un.character_id is None and not un.is_primary
    with pytest.raises(ReferenceLibraryError):
        lib.mark_primary("hero_v2")  # 未綁角色不可設 primary


def test_character_store_crud_without_hard_delete(tmp_path):
    st = CharacterStore(tmp_path)
    rec = st.create(CharacterDefinition(character_id="char_001", display_name="男主角", gender_presentation=GenderPresentation.male))
    assert rec.revision == 1 and st.get("char_001").definition.display_name == "男主角"
    with pytest.raises(CharacterStoreError):
        st.create(CharacterDefinition(character_id="char_001", display_name="x"))
    up = st.update("char_001", outfit="grey suit")
    assert up.revision == 2 and up.definition.outfit == "grey suit" and up.created_at == rec.created_at
    assert st.update("char_001", outfit="grey suit").revision == 2  # 無實際變更 → 不遞增
    with pytest.raises(CharacterStoreError):
        st.update("char_001", character_id="char_009")
    with pytest.raises(ValueError):
        st.update("char_001", gender_presentation="man")  # 只收顯式 enum
    st.archive("char_001")
    assert st.list() == [] and st.list(include_archived=True)[0].archived
    with pytest.raises(CharacterStoreError):
        st.update("char_001", outfit="x")
    assert not st.restore("char_001").archived and (tmp_path / "character_library" / "char_001.json").exists()
    assert not hasattr(st, "delete")
    with pytest.raises(CharacterStoreError):
        st.get("../etc")


def test_confirmation_payload_rows_and_fail_closed(lib):
    lib.register("people/hero_v1.jpg", asset_id="hero_v1", role=RefRole.identity_face, source_type="user_supplied", character_id="char_001")
    lib.mark_primary("hero_v1")
    chars = [CharacterDefinition(character_id="char_001", display_name="男主角", gender_presentation=GenderPresentation.male,
                                 outfit="grey suit", default_style_profile="realistic", voice_profile=VoiceAssignment(voice_id="zm_010")),
             CharacterDefinition(character_id="char_002", display_name="女主角", gender_presentation=GenderPresentation.female,
                                 outfit="red coat")]
    places = [ScenePlacement(character_id="char_001", horizontal=Horizontal.left),
              ScenePlacement(character_id="char_002", horizontal=Horizontal.right)]
    pay = confirmation_payload(chars, lib.assets_for("char_001"), places, scene_mood="warm", scene_voice={"char_002": "zf_001"})
    a, b = pay.rows
    assert (a.display_name, a.gender_presentation.value, a.outfit, a.style, a.mood, a.voice) == ("男主角", "male", "grey suit", "realistic", "warm", "zm_010")
    assert a.primary_reference["file_name"] == "hero_v1.jpg" and a.placement["horizontal"] == "left"
    assert b.primary_reference is None and b.style is None and b.voice == "zf_001"  # 缺值保持 None，不補值
    assert pay.can_generate  # 授權 unknown 在內部診斷只是警告
    bad = confirmation_payload(chars, lib.assets_for("char_001"), places[:1])  # char_002 沒有 placement
    assert not bad.can_generate and any(i.code == "placement_missing" for i in bad.issues)
    final = confirmation_payload(chars, lib.assets_for("char_001"), places, final_output=True)
    assert not final.can_generate  # 正式輸出：商用授權 unknown → 擋


def test_ref_cli(tmp_path, monkeypatch, capsys):
    from see.app.cli import main

    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path))
    _img(tmp_path / "reference_library" / "people" / "a.jpg", (1, 2, 3))
    assert main(["ref", "register", "people/a.jpg", "--asset-id", "a", "--role", "identity_face", "--source-type",
                 "user_supplied", "--character", "char_001"]) == 0
    assert main(["ref", "primary", "a"]) == 0
    capsys.readouterr()
    assert main(["ref", "list"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["asset"]["is_primary"] and out[0]["support"] != "not yet supported"
    assert main(["ref", "bind", "a", "--unbind"]) == 0
    assert main(["ref", "primary", "a"]) == 2  # 未綁角色 → fail closed
