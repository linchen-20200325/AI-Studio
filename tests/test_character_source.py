"""D-073 Batch 6A：production character source（legacy Project.characters｜pinned Project.cast）。合成專案；不碰真實專案。"""
from __future__ import annotations

import json

import pytest

from see.core import character_migration_apply as cma
from see.core import migration_decisions as md
from see.core.character_migration import analyze
from see.core.character_source import CAST, LEGACY, CharacterSourceError
from see.models.character_definition import VoiceAssignment
from see.models.project import CharacterAppearance, CharacterVoice
from see.models.script import Character
from see.storage.character_store import CharacterStore
from tests.conftest import TINY_STORY

PID = "src6a"
NAMES = {"char_01": "阿光", "char_02": "小雨"}


def _migrate(orch, tmp_path, bind_lib: str | None = None):
    p = orch.create_project(TINY_STORY, project_id=PID)
    orch.write_script(p)
    orch.storyboard(p)
    p.characters = {}
    p.script.characters = [Character(character_id=c, name=n, description="", visual_prompt="") for c, n in NAMES.items()]
    for s in p.scenes:
        s.character_ids = ["char_01", "char_02"]
    orch.store.save(p)
    ws = orch.settings.workspace
    base = analyze(PID, ws)
    doc = md.decisions_template(base)
    doc["decisions"] = [{"legacy_id": "char_02", "action": "create_new"}]
    doc["decisions"].append({"legacy_id": "char_01", "action": "bind_existing", "library_character_id": bind_lib, "library_revision": 1}
                            if bind_lib else {"legacy_id": "char_01", "action": "create_new"})
    f = tmp_path / "d.json"
    f.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    d, errs, dsha = md.load_decisions(f)
    token = md.apply_decisions(base, d, CharacterStore(ws), load_errors=errs, decisions_file_sha256=dsha)["report"]["summary"]["apply_confirmation_token"]
    rec = cma.apply(PID, ws, f, token)
    return rec, {x["legacy_id"]: x["character_id"] for x in rec["legacy_to_library"]}


@pytest.fixture
def pinned(orchestrator, tmp_path):
    """char_01 綁既有 Library 角色 r1（短髮、zm_010）；之後 Library 升到 r2（長髮、zm_011）→ production 必須仍用 r1。"""
    cs = CharacterStore(orchestrator.settings.workspace)
    lib = cs.create_new(display_name="阿光", hair_style="short", voice_profile=VoiceAssignment(voice_id="zm_010", speed=1.1)
                        ).definition.character_id
    rec, m = _migrate(orchestrator, tmp_path, bind_lib=lib)
    cs.update(lib, hair_style="long", voice_profile=VoiceAssignment(voice_id="zm_011"))
    assert cs.list_revisions(lib) == [1, 2]
    return orchestrator, rec, m, lib


def test_cast_mode_uses_pinned_revision_not_latest(pinned):
    orch, rec, m, lib = pinned
    p = orch.store.load(PID)
    src = orch.character_source(p)
    assert src.mode == CAST and src.migration_id == rec["migration_id"] and src.cast[lib].character_revision == 1
    req, ctx = orch.image_request(p, p.scenes[0])
    assert ctx["character_source"] == CAST and "short hair" in req.prompt and "long" not in req.prompt
    ref = req.params["characters"][0]
    assert ref["character_id"] == lib and ref["character_revision"] == 1 and ref["content_sha256"] == src.cast[lib].content_sha256
    s = p.scenes[0]
    s.narrator_id = lib
    assert orch.resolve_voice(p, s) == ("zm_010", 1.1, f"cast:{lib}@r1")  # r1，不是 latest r2 的 zm_011


def test_project_characters_edits_do_not_affect_migrated_project(pinned):
    orch, _, m, lib = pinned
    p = orch.store.load(PID)
    s = p.scenes[0]
    s.narrator_id = lib
    req0, _ = orch.image_request(p, s)
    v0 = orch.resolve_voice(p, s)
    p.characters[lib] = CharacterVoice(character_id=lib, voice_id="zm_099", speed=1.5, confirmed=True,
                                       appearance=CharacterAppearance(outfit_en="red armor"))
    req1, _ = orch.image_request(p, s)
    assert req1.model_dump() == req0.model_dump() and orch.resolve_voice(p, s) == v0
    assert orch.unconfirmed_characters(p) == [lib]  # legacy confirmed 不被沿用；cast 層確認尚無 schema → 視為未確認


def test_new_character_without_voice_profile_is_not_filled(orchestrator, tmp_path):
    _, m = _migrate(orchestrator, tmp_path)
    p = orchestrator.store.load(PID)
    s = p.scenes[0]
    req, ctx = orchestrator.image_request(p, s)
    assert ctx["character_source"] == CAST and req.params == {}  # 只有名稱、無外觀 → 不補 anchor（與遷移前相同）
    s.narrator_id = m["char_02"]
    assert orchestrator.resolve_voice(p, s) == ("default", p.speech_speed, "provider-default")


def test_legacy_project_unchanged(orchestrator):
    p = orchestrator.create_project(TINY_STORY, project_id="leg")
    orchestrator.write_script(p)
    orchestrator.storyboard(p)
    orchestrator.set_character(p, "hero", voice_id="zm_010", speed=1.2)
    orchestrator.set_character_appearance(p, "hero", CharacterAppearance(outfit_en="grey suit"))
    orchestrator.update_scene(p, p.scenes[0].scene_id, character_ids=["hero"], narrator_id="hero")
    s = p.scene(p.scenes[0].scene_id)
    assert orchestrator.character_source(p).mode == LEGACY
    req, _ = orchestrator.image_request(p, s)
    assert req.params["characters"] == [{"character_id": "hero", "anchor": "wearing grey suit", "reference_images": [], "seed": None,
                                         "adapter": {}}]  # legacy 結構不變（fingerprint 相容）
    assert orchestrator.resolve_voice(p, s) == ("zm_010", 1.2, "character:hero") and orchestrator.unconfirmed_characters(p) == ["hero"]


def _rec_path(orch, rec):
    return cma.migrations_dir(orch.settings.workspace, PID) / f"{rec['migration_id']}.json"


def _expect(orch, code):
    p = orch.store.load(PID)
    for fn in (lambda: orch.image_request(p, p.scenes[0]), lambda: orch.unconfirmed_characters(p)):
        with pytest.raises(CharacterSourceError) as e:
            fn()
        assert e.value.code == code, e.value


def test_fail_closed_tampered_revision_and_partial(pinned):
    orch, rec, m, lib = pinned
    cs = CharacterStore(orch.settings.workspace)
    other = m["char_02"]
    f = cs.root / "history" / other / "r000001.json"
    data = json.loads(f.read_text(encoding="utf-8"))
    data["definition"]["display_name"] = "被竄改"
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _expect(orch, "CAST_RESOLUTION_FAILED")  # 一筆失敗 → 整體 fail closed（不部分使用、不 fallback legacy）


def test_fail_closed_missing_character_and_revision(pinned):
    orch, rec, m, lib = pinned
    cs = CharacterStore(orch.settings.workspace)
    other = m["char_02"]
    (cs.root / "history" / other / "r000001.json").rename(cs.root / "moved.json")
    _expect(orch, "CAST_RESOLUTION_FAILED")  # revision 不存在（不 fallback latest）
    (cs.root / "moved.json").rename(cs.root / "history" / other / "r000001.json")
    p = orch.store.load(PID)
    rp = _rec_path(orch, rec)
    r = json.loads(rp.read_text(encoding="utf-8"))
    for c in r["cast"]:
        if c["character_id"] == other:
            c["character_id"] = "char_000000000000"
    rp.write_text(json.dumps(r), encoding="utf-8")
    for b in p.cast:
        if b.character_id == other:
            b.character_id = "char_000000000000"
    orch.store.save(p)
    _expect(orch, "CAST_RESOLUTION_FAILED")  # character_id 不存在


def test_fail_closed_migration_state_inconsistent(pinned):
    orch, rec, m, lib = pinned
    rp = _rec_path(orch, rec)
    r = json.loads(rp.read_text(encoding="utf-8"))
    r["status"] = "committing"
    rp.write_text(json.dumps(r), encoding="utf-8")
    _expect(orch, "MIGRATION_RECORD_INCOMPLETE")
    r["status"] = "committed"
    rp.write_text(json.dumps(r), encoding="utf-8")
    p = orch.store.load(PID)
    keep = list(p.cast)
    p.cast = keep[:1]  # cast 與 record 不一致
    orch.store.save(p)
    _expect(orch, "CAST_MIGRATION_STATE_INCONSISTENT")
    p.cast = []  # committed record 但 cast 為空
    orch.store.save(p)
    _expect(orch, "CAST_MIGRATION_STATE_INCONSISTENT")


def test_fail_closed_scene_reference_not_in_cast(pinned):
    orch, rec, m, lib = pinned
    p = orch.store.load(PID)
    s = p.scenes[0]
    s.character_ids = ["char_01"]  # legacy ID 殘留／不在 cast
    with pytest.raises(CharacterSourceError) as e:
        orch.image_request(p, s)
    assert e.value.code == "CAST_REFERENCE_NOT_IN_CAST"
    s.character_ids = []
    s.narrator_id = "hero"
    with pytest.raises(CharacterSourceError):
        orch.resolve_voice(p, s)
    with pytest.raises(ValueError):
        orch.update_scene(p, s.scene_id, narrator_id="hero")  # cast 模式下 narrator 必須在 cast


def test_rollback_returns_to_legacy(orchestrator, tmp_path):
    rec, _ = _migrate(orchestrator, tmp_path)
    assert orchestrator.character_source(orchestrator.store.load(PID)).mode == CAST
    cma.rollback(PID, orchestrator.settings.workspace, rec["migration_id"])
    assert orchestrator.character_source(orchestrator.store.load(PID)).mode == LEGACY
