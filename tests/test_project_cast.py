"""D-068 Batch 3：Project.cast foundation（可選、預設空、不影響 pipeline）＋pinned revision 解析。
Project.cast exists but is not yet production source of truth。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from see.core.cast import resolve_project_cast
from see.core.reference_library import ReferenceLibrary
from see.models.character_binding import CharacterBinding
from see.models.character_definition import ID_PATTERN, RefRole
from see.models.project import Project
from see.storage.character_store import CharacterStore
from tests.conftest import TINY_STORY, requires_ffmpeg


def _planned(orch, pid):
    p = orch.create_project(TINY_STORY, project_id=pid)
    orch.write_script(p)
    orch.storyboard(p)
    return p


def _img(path: Path, color) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), color).save(path)
    return path


def _char_at_r7(store: CharacterStore) -> str:
    cid = store.create_new(display_name="女主角", hair_style="長髮").definition.character_id
    for i in range(6):
        store.update(cid, notes=f"v{i + 2}")
    assert store.list_revisions(cid)[-1] == 7
    return cid


def test_empty_cast_default_and_old_project_json_compat(orchestrator):
    p = _planned(orchestrator, "c0")
    assert p.cast == [] and p.cast_schema_version is None
    f = orchestrator.store.project_file("c0")
    raw = json.loads(f.read_text(encoding="utf-8"))
    raw.pop("cast")
    raw.pop("cast_schema_version")  # 模擬 D-068 之前的 project.json
    f.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    before = f.read_bytes()
    old = orchestrator.store.load("c0")
    assert old.cast == [] and f.read_bytes() == before  # 讀取不寫回
    assert resolve_project_cast(old, CharacterStore(orchestrator.settings.workspace)).status == "not_configured"


def test_cast_validation():
    base = {"project_id": "x", "input_text": "a"}
    p = Project(**base, cast=[{"character_id": "char_aaaaaaaaaaaa", "character_revision": 3, "role_label": "男主角", "alias": "阿明"}])
    assert p.cast_schema_version == 1 and p.cast[0].follow == "pinned"
    bad = [
        [{"character_id": "char_a1", "character_revision": 1}, {"character_id": "char_a1", "character_revision": 2}],  # 重複
        [{"character_id": "char_a1", "character_revision": 0}],  # revision 必須 > 0
        [{"character_id": "Char-A", "character_revision": 1}],  # ID 格式
        [{"character_id": "char_a1"}],  # 不可省略 revision（不會自動用 latest）
        [{"character_id": "char_a1", "character_revision": 1, "follow": "latest"}],
        [{"character_id": "char_a1", "character_revision": 1, "role_label": "x" * 41}],
    ]
    for c in bad:
        with pytest.raises(ValidationError):
            Project(**base, cast=c)
    with pytest.raises(ValidationError, match="newer than supported"):  # 未來格式 → fail safe
        Project(**base, cast=[{"character_id": "char_a1", "character_revision": 1}], cast_schema_version=99)
    from see.models import character_binding

    assert character_binding.ID_PATTERN == ID_PATTERN


def test_pinned_r3_after_r7_survives_reopen(orchestrator):
    ws = orchestrator.settings.workspace
    store = CharacterStore(ws)
    cid = _char_at_r7(store)
    p = _planned(orchestrator, "c1")
    p.cast = [CharacterBinding(character_id=cid, character_revision=3, role_label="女主角")]
    orchestrator.store.save(p)
    store.update(cid, hair_style="短髮")  # head 繼續變（r8）
    reopened = orchestrator.store.load("c1")
    assert reopened.cast[0].character_revision == 3
    rep = resolve_project_cast(reopened, store)
    e = rep.entries[0]
    assert rep.status == "ok" and e.resolved_revision == 3 and e.snapshot["notes"] == "v3" and e.snapshot["hair_style"] == "長髮"
    assert e.content_sha256 == store.read_revision(cid, 3).content_sha256


def test_missing_and_tampered_revision_fail_closed(orchestrator):
    ws = orchestrator.settings.workspace
    store = CharacterStore(ws)
    cid = _char_at_r7(store)
    p = Project(project_id="c2", input_text="a", cast=[CharacterBinding(character_id=cid, character_revision=12)])
    rep = resolve_project_cast(p, store)
    assert rep.status == "error" and rep.entries[0].integrity == "error" and rep.entries[0].resolved_revision is None
    assert rep.entries[0].snapshot is None  # 不 fallback latest
    f = store.root / "history" / cid / "r000003.json"
    raw = json.loads(f.read_text())
    raw["definition"]["hair_style"] = "被改"
    f.write_text(json.dumps(raw))
    rep = resolve_project_cast(Project(project_id="c2", input_text="a", cast=[CharacterBinding(character_id=cid, character_revision=3)]), store)
    assert rep.status == "error" and "content_sha256 mismatch" in rep.entries[0].error
    ghost = Project(project_id="c2", input_text="a", cast=[CharacterBinding(character_id="char_nothere", character_revision=1)])
    assert resolve_project_cast(ghost, store).status == "error"


def test_missing_reference_not_ready_and_archived_revision_resolves(orchestrator):
    ws = orchestrator.settings.workspace
    store = CharacterStore(ws)
    lib = ReferenceLibrary(ws)
    cid = store.create_new(display_name="男主角").definition.character_id
    img = _img(ws / "reference_library" / "people" / "hero.jpg", (5, 5, 5))
    lib.register("people/hero.jpg", asset_id="hero_face", role=RefRole.identity_face, source_type="user_supplied", character_id=cid)
    store.refresh_references(cid)  # r2：凍結 hero_face
    store.archive(cid)  # r3
    p = Project(project_id="c3", input_text="a", cast=[CharacterBinding(character_id=cid, character_revision=2)])
    rep = resolve_project_cast(p, store, lib)
    assert rep.status == "ok" and rep.entries[0].archived is False  # archive 前的 revision 照常解析
    arch = resolve_project_cast(Project(project_id="c3", input_text="a", cast=[CharacterBinding(character_id=cid, character_revision=3)]), store)
    assert arch.entries[0].integrity == "ok" and arch.entries[0].archived is True
    img.unlink()
    rep = resolve_project_cast(p, store, lib)
    assert rep.status == "partial" and not rep.generation_ready
    assert rep.entries[0].missing_references == ["hero_face"] and rep.entries[0].integrity == "ok"


def test_cast_does_not_touch_production_pipeline(orchestrator):
    """有 cast（甚至指向不存在的 revision）時，image request／voice／fingerprint 與沒有 cast 時完全相同。"""
    p = _planned(orchestrator, "c4")
    orchestrator.set_character(p, "hero", display_name="英雄", voice_id="zm_010")
    orchestrator.set_character_appearance(p, "hero", None)
    orchestrator.update_scene(p, p.scenes[0].scene_id, character_ids=["hero"], narrator_id="hero")
    s = p.scene(p.scenes[0].scene_id)
    req0, ctx0 = orchestrator.image_request(p, s)
    voice0 = orchestrator.resolve_voice(p, s)
    unconfirmed0 = orchestrator.unconfirmed_characters(p)
    p.cast = [CharacterBinding(character_id="char_nothere", character_revision=5, role_label="男主角")]
    req1, ctx1 = orchestrator.image_request(p, s)
    assert req1.model_dump() == req0.model_dump() and ctx1 == ctx0
    assert orchestrator.resolve_voice(p, s) == voice0 and orchestrator.unconfirmed_characters(p) == unconfirmed0
    assert "char_nothere" not in json.dumps(req1.model_dump(), ensure_ascii=False)


@requires_ffmpeg
def test_empty_or_filled_cast_does_not_change_fingerprints(orchestrator):
    p = _planned(orchestrator, "c5")
    orchestrator.build_scene_assets(p)
    fps = {s.scene_id: {k: v.fingerprint for k, v in orchestrator.store.load_manifest("c5", s.scene_id).entries.items()} for s in p.scenes}
    p.cast = [CharacterBinding(character_id="char_nothere", character_revision=1)]
    orchestrator.store.save(p)
    reps = orchestrator.build_scene_assets(orchestrator.store.load("c5"))
    assert all(r.rebuilt == [] for r in reps)
    assert {s.scene_id: {k: v.fingerprint for k, v in orchestrator.store.load_manifest("c5", s.scene_id).entries.items()} for s in p.scenes} == fps


def test_doctor_and_export_cast_info(orchestrator, monkeypatch, tmp_path):
    from see.core import environment as env

    monkeypatch.setattr(env, "gpu_info", lambda: {"torch": None, "cuda_available": False, "cuda_build": None, "cudnn": None,
                                                    "devices": [], "source": "x"})
    s = orchestrator.settings
    ws = s.workspace
    _planned(orchestrator, "c6")
    chk = {c.key: c for c in env.run_doctor(s, env={}).checks}["workspace.project_cast"]
    assert chk.status == env.Status.UNAVAILABLE and "not configured" in chk.detail and "workspace.project_cast" not in env.run_doctor(s, env={}).failed_required
    store = CharacterStore(ws)
    cid = _char_at_r7(store)
    p = orchestrator.store.load("c6")
    p.cast = [CharacterBinding(character_id=cid, character_revision=3, role_label="女主角", alias="小美")]
    orchestrator.store.save(p)
    assert {c.key: c for c in env.run_doctor(s, env={}).checks}["workspace.project_cast"].status == env.Status.OK
    out = env.export_environment(s, out_dir=tmp_path / "exp")
    inv = json.loads((out / "workspace_inventory.json").read_text())
    cast = [x for x in inv["projects"] if x["project_id"] == "c6"][0]["cast"]
    e = cast["entries"][0]
    assert cast["status"] == "ok" and e["binding"] == {"character_id": cid, "character_revision": 3, "role_label": "女主角", "alias": "小美", "follow": "pinned"}
    assert e["content_sha256"] == store.read_revision(cid, 3).content_sha256 and e["generation_ready"] is True and "snapshot" not in e
    p.cast = [CharacterBinding(character_id=cid, character_revision=40)]
    orchestrator.store.save(p)
    bad = {c.key: c for c in env.run_doctor(s, env={}).checks}["workspace.project_cast"]
    assert bad.status == env.Status.ERROR and not bad.required


def test_cast_cli_and_api_are_read_only(orchestrator, monkeypatch, capsys):
    from see.app.cli import main

    ws = orchestrator.settings.workspace
    monkeypatch.setenv("SEE_WORKSPACE", str(ws))
    store = CharacterStore(ws)
    cid = _char_at_r7(store)
    p = _planned(orchestrator, "c7")
    p.cast = [CharacterBinding(character_id=cid, character_revision=3, role_label="女主角")]
    orchestrator.store.save(p)
    before = orchestrator.store.project_file("c7").read_bytes()
    assert main(["cast", "show", "c7"]) == 0
    out = capsys.readouterr().out
    assert f"{cid}@r3" in out and "[OK]" in out and "Project.characters" in out
    assert orchestrator.store.project_file("c7").read_bytes() == before
    from fastapi.testclient import TestClient

    from see.ui.server import create_app

    c = TestClient(create_app(orchestrator.settings, sync_jobs=True))
    r = c.get("/api/projects/c7/cast").json()
    assert r["production_source"] == "Project.characters" and r["entries"][0]["resolved_revision"] == 3
    assert orchestrator.store.project_file("c7").read_bytes() == before
