"""D-067 Batch 2：Character Store 不可變 revision history、canonical hash、reference snapshot、legacy baseline、CharacterBinding（pinning）。"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from PIL import Image

from see.core.reference_library import ReferenceLibrary
from see.models.character_binding import CharacterBinding, resolve_binding
from see.models.character_definition import ID_PATTERN, CharacterDefinition, RefRole
from see.storage.character_store import (CharacterRevisionError, CharacterStore, CharacterStoreError, canonical_hash,
                                         new_character_id)


def _img(path: Path, color) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), color).save(path)
    return path


@pytest.fixture
def store(tmp_path) -> CharacterStore:
    return CharacterStore(tmp_path / "ws")


def _rev_file(store, cid, n) -> Path:
    return store.root / "history" / cid / f"r{n:06d}.json"


def test_create_update_rename_archive_restore_produce_monotonic_immutable_revisions(store):
    rec = store.create_new(display_name="男主角", outfit="灰西裝")
    cid = rec.definition.character_id
    assert re.fullmatch(ID_PATTERN, cid) and cid.startswith("char_") and "男" not in cid
    assert rec.revision == 1 and store.list_revisions(cid) == [1]
    r1_bytes = _rev_file(store, cid, 1).read_bytes()
    r1 = store.read_revision(cid, 1)
    store.update(cid, outfit="黑色大衣")
    assert store.list_revisions(cid) == [1, 2] and _rev_file(store, cid, 1).read_bytes() == r1_bytes  # 舊 revision 位元不變
    assert store.read_revision(cid, 1) == r1 and store.read_revision(cid, 2).definition.outfit == "黑色大衣"
    store.update(cid, display_name="阿明")  # rename
    assert store.get(cid).definition.character_id == cid and store.read_revision(cid, 3).provenance["action"] == "rename"
    assert store.update(cid, display_name="阿明").revision == 3  # 沒有實際變更 → 不產生 revision
    store.archive(cid)
    store.restore(cid)
    revs = [store.read_revision(cid, n) for n in store.list_revisions(cid)]
    assert [r.revision for r in revs] == [1, 2, 3, 4, 5]
    assert [r.provenance["action"] for r in revs] == ["create", "update", "rename", "archive", "restore"]
    assert [r.archived for r in revs] == [False, False, False, True, False]
    assert [r.provenance["previous_revision"] for r in revs] == [None, 1, 2, 3, 4]
    assert store.read_revision(cid, 3).archived is False  # archive 之前的 revision 永遠可解析
    with pytest.raises(CharacterStoreError):
        store.create_new(character_id="char_custom", display_name="x")  # ID 由系統產生


def test_no_hard_delete_and_no_overwrite_api(store):
    names = {n for n in dir(CharacterStore) if not n.startswith("__")}
    assert not names & {"delete", "remove", "hard_delete", "purge", "delete_revision", "update_revision", "write_revision"}
    rec = store.create_new(display_name="A")
    cid = rec.definition.character_id
    from see.storage.character_store import CharacterRecord

    with pytest.raises(CharacterRevisionError):  # 同號 revision 已存在 → 拒絕（exclusive create）
        store._append(CharacterRecord(definition=rec.definition, revision=1), "update", None)


def test_canonical_hash_is_deterministic_and_order_independent():
    a = {"b": 1, "a": {"y": [1, 2], "x": "中文"}}
    b = {"a": {"x": "中文", "y": [1, 2]}, "b": 1}
    assert canonical_hash(a) == canonical_hash(b) and len(canonical_hash(a)) == 64
    assert canonical_hash(a) != canonical_hash({**a, "b": 2})


def test_tampered_revision_fails_closed_without_repair(store):
    cid = store.create_new(display_name="A").definition.character_id
    store.update(cid, outfit="x")
    f = _rev_file(store, cid, 1)
    raw = json.loads(f.read_text())
    raw["definition"]["outfit"] = "被改過"
    f.write_text(json.dumps(raw))
    tampered = f.read_text()
    with pytest.raises(CharacterRevisionError, match="content_sha256 mismatch"):
        store.read_revision(cid, 1)
    assert store.verify_revision(cid, 1) and store.verify_revision(cid, 2) == []
    assert f.read_text() == tampered  # 不自動修復
    f2 = _rev_file(store, cid, 2)
    raw2 = json.loads(f2.read_text())
    raw2["archived"] = True
    f2.write_text(json.dumps(raw2))
    with pytest.raises(CharacterRevisionError):
        store.update(cid, outfit="y")  # 最新 revision 被竄改 → 不在其上繼續寫
    with pytest.raises(CharacterRevisionError):
        store.get(cid)


def test_reference_snapshot_is_frozen_per_revision_and_portable(store, tmp_path):
    ws = store.workspace
    lib = ReferenceLibrary(ws)
    cid = store.create_new(display_name="男主角").definition.character_id
    _img(ws / "reference_library" / "people" / "face_v1.jpg", (10, 10, 10))
    lib.register("people/face_v1.jpg", asset_id="face_v1", role=RefRole.identity_face, source_type="user_supplied", character_id=cid)
    lib.mark_primary("face_v1")
    r2 = store.refresh_references(cid)
    assert r2.revision == 2 and store.refresh_references(cid).revision == 2  # 沒變 → 不產生 revision
    snap2 = store.read_revision(cid, 2)
    assert snap2.primary_reference_asset_id == "face_v1" and snap2.reference_asset_ids == ["face_v1"]
    b = snap2.reference_bindings[0]
    assert (b.status, b.rel_path, b.role, b.is_primary) == ("ok", "people/face_v1.jpg", "identity_face", True) and len(b.sha256) == 64
    assert store.read_revision(cid, 1).reference_bindings == []  # 舊 revision 不受影響
    # 換主要 reference → 新 revision；r2 不變
    _img(ws / "reference_library" / "people" / "face_v2.jpg", (99, 99, 99))
    lib.register("people/face_v2.jpg", asset_id="face_v2", role=RefRole.identity_face, source_type="user_supplied", character_id=cid)
    lib.mark_primary("face_v2")
    store.refresh_references(cid)
    r3 = store.read_revision(cid, 3)
    assert r3.primary_reference_asset_id == "face_v2" and store.read_revision(cid, 2).primary_reference_asset_id == "face_v1"
    # 可攜：revision 檔不含本機絕對路徑
    for n in store.list_revisions(cid):
        text = _rev_file(store, cid, n).read_text(encoding="utf-8")
        assert str(tmp_path) not in text and str(Path.home()) not in text
    # definition 列了但 Library 找不到的 asset → missing（sha256=None，不補造）
    store.update(cid, reference_asset_ids=["ghost_ref"])
    ghost = [x for x in store.read_revision(cid, 4).reference_bindings if x.asset_id == "ghost_ref"][0]
    assert ghost.status == "missing" and ghost.sha256 is None and ghost.rel_path is None


def test_pinned_binding_resolves_old_revision_and_never_falls_back_to_latest(store):
    ws = store.workspace
    cid = store.create_new(display_name="女主角", hair_style="長髮").definition.character_id
    for i in range(6):
        store.update(cid, notes=f"v{i}")
    assert store.list_revisions(cid)[-1] == 7
    res = resolve_binding(store, CharacterBinding(character_id=cid, character_revision=3, role_label="女主角"))
    assert res.revision.revision == 3 and res.revision.definition.notes == "v1" and res.generation_ready
    with pytest.raises(CharacterRevisionError):
        resolve_binding(store, CharacterBinding(character_id=cid, character_revision=99))  # 不存在 → fail closed，不用 latest
    f = _rev_file(store, cid, 3)
    raw = json.loads(f.read_text())
    raw["definition"]["hair_style"] = "短髮"
    f.write_text(json.dumps(raw))
    with pytest.raises(CharacterRevisionError):
        resolve_binding(store, CharacterBinding(character_id=cid, character_revision=3))  # hash 不符 → fail closed
    with pytest.raises(ValueError):
        CharacterBinding(character_id=cid, character_revision=3, follow="latest")  # 跟隨最新版不是預設、目前不允許
    assert (ws / "character_library").is_dir()


def test_missing_old_reference_blocks_generation_but_never_rebinds(store):
    ws = store.workspace
    lib = ReferenceLibrary(ws)
    cid = store.create_new(display_name="A").definition.character_id
    old = _img(ws / "reference_library" / "people" / "old.jpg", (1, 2, 3))
    lib.register("people/old.jpg", asset_id="old", role=RefRole.identity_face, source_type="user_supplied", character_id=cid)
    lib.mark_primary("old")
    store.refresh_references(cid)  # r2：old
    _img(ws / "reference_library" / "people" / "new.jpg", (4, 5, 6))
    lib.register("people/new.jpg", asset_id="new", role=RefRole.identity_face, source_type="user_supplied", character_id=cid)
    old.unlink()  # 私人圖片遺失
    res = resolve_binding(store, CharacterBinding(character_id=cid, character_revision=2))
    assert res.revision.revision == 2 and not res.generation_ready and res.missing_assets == ["old"]
    assert [b.asset_id for b in res.revision.reference_bindings] == ["old"]  # 不改綁 new.jpg


def test_legacy_store_gets_baseline_without_fabricated_history(store):
    """D-067 前的 Character Store：只有 head（revision 3），沒有 history。"""
    from see.storage.character_store import CharacterRecord

    store.root.mkdir(parents=True)
    legacy = CharacterRecord(definition=CharacterDefinition(character_id="char_001", display_name="舊角色"), revision=3)
    raw = json.loads(legacy.model_dump_json())
    raw.pop("schema_version")  # 更舊的 head（無 schema_version）
    (store.root / "char_001.json").write_text(json.dumps(raw))
    assert store.get("char_001").revision == 3 and store.list_revisions("char_001") == []  # 讀取不寫入
    assert store.migration_plan()["no_history"] == ["char_001.json"]
    store.update("char_001", outfit="新衣")
    assert store.list_revisions("char_001") == [3, 4]  # baseline＝當下 head（r3）；r1、r2 不存在、不補造
    base = store.read_revision("char_001", 3)
    assert base.provenance["baseline_from_legacy_current"] is True and "不存在" in base.provenance["note"]
    assert base.definition.outfit == "" and store.read_revision("char_001", 4).definition.outfit == "新衣"
    with pytest.raises(CharacterRevisionError, match="早於 history 起點"):
        store.read_revision("char_001", 1)


def test_future_revision_schema_fails_safely(store):
    cid = store.create_new(display_name="A").definition.character_id
    f = _rev_file(store, cid, 1)
    raw = json.loads(f.read_text())
    raw["schema_version"] = 99
    f.write_text(json.dumps(raw))
    with pytest.raises(CharacterRevisionError, match="newer than supported"):
        store.read_revision(cid, 1)


def test_doctor_reports_history_integrity(store, monkeypatch):
    from see.core import environment as env
    from see.core.config import Settings

    monkeypatch.setattr(env, "gpu_info", lambda: {"torch": None, "cuda_available": False, "cuda_build": None, "cudnn": None,
                                                    "devices": [], "source": "x"})
    cid = store.create_new(display_name="A").definition.character_id
    s = Settings()
    s.workspace = store.workspace
    ok = {c.key: c for c in env.run_doctor(s, env={}).checks}["workspace.character_store"]
    assert ok.status == env.Status.OK
    f = _rev_file(store, cid, 1)
    f.write_text(f.read_text().replace('"A"', '"B"'))
    bad = {c.key: c for c in env.run_doctor(s, env={}).checks}["workspace.character_store"]
    assert bad.status == env.Status.ERROR


def test_new_ids_are_unique_and_pattern_valid():
    ids = {new_character_id() for _ in range(200)}
    assert len(ids) == 200 and all(re.fullmatch(ID_PATTERN, i) for i in ids)
