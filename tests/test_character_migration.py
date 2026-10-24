"""D-069 Batch 4：character-migrate --dry-run（只分析）。Batch 4 only analyzes. No project has been migrated."""
from __future__ import annotations

import json

import pytest

from see.core.character_migration import (CONFLICTS, MIGRATION_REPORT_SCHEMA_VERSION, PENDING_ID, analyze, workspace_digest)
from tests import migration_fixture as fx
from tests.conftest import TINY_STORY, requires_ffmpeg


@pytest.fixture
def mig(orchestrator, tmp_path):
    private = tmp_path / "private_refs"
    private.mkdir()
    pid = fx.build(orchestrator, private, TINY_STORY)
    return orchestrator, pid


def _entries(res):
    return {e["legacy_id"]: e for e in res["report"]["entries"]}


def _codes(e):
    return {c["code"] for c in e["conflicts"]}


def test_classification_rules(mig):
    orch, pid = mig
    e = _entries(analyze(pid, orch.settings.workspace))
    assert e["narrator"]["classification"] == "NARRATOR_SETTING" and e["narrator"]["is_narrator_or_voice_only"]
    assert e["narrator"]["proposed_action"] == "propose_project_narrator_setting" and e["narrator"]["proposed_character_id"] is None
    assert "NARRATOR_NOT_CHARACTER" in _codes(e["narrator"])
    assert e["ghost"]["classification"] == "EMPTY_UNUSED" and "EMPTY_CHARACTER" in _codes(e["ghost"])
    assert e["model_only"]["classification"] == "LEGACY_ONLY"
    assert e["model_only"]["legacy_only_fields"] == ["appearance.adapter", "appearance.seed"]
    assert not [c for c in e["model_only"]["conflicts"] if c["severity"] == "blocking"] and e["model_only"]["rewrite_count"] == 0
    assert e["ghost"]["rewrite_count"] == 0 and not e["ghost"]["requires_human_decision"]  # 未被引用的空條目：留在 legacy
    assert e["both"]["classification"] == "HUMAN_REQUIRED" and "VOICE_ROLE_AMBIGUOUS" in _codes(e["both"])
    for v in e.values():
        assert v["classification"] in ("AUTO_MAPPABLE", "HUMAN_REQUIRED", "LEGACY_ONLY", "NARRATOR_SETTING", "EMPTY_UNUSED")
        assert {c["code"] for c in v["conflicts"]} <= set(CONFLICTS)  # 只有固定 code


def test_gender_age_free_text_never_auto_converted(mig):
    orch, pid = mig
    hero = _entries(analyze(pid, orch.settings.workspace))["hero"]
    assert hero["classification"] == "HUMAN_REQUIRED" and hero["requires_human_decision"]
    assert {"GENDER_MAPPING_AMBIGUOUS", "AGE_MAPPING_AMBIGUOUS"} <= _codes(hero)
    m = {x["source"]: x for x in hero["field_mappings"]}
    assert m["appearance.traits.gender_presentation"]["status"] == "human" and m["appearance.traits.age"]["status"] == "human"
    assert m["appearance.outfit_en"] == {"source": "appearance.outfit_en", "target": "outfit", "status": "auto", "value": "grey suit"}
    assert m["appearance.traits.hair_style"]["target"] == "hair_style" and m["voice_id"]["target"] == "voice_profile.voice_id"
    assert "VOICE_CONFIRMATION_REBIND" in _codes(hero)


def test_same_name_is_never_an_auto_match(mig):
    orch, pid = mig
    hero = _entries(analyze(pid, orch.settings.workspace))["hero"]
    name_c = [c for c in hero["conflicts"] if c["code"] == "NAME_CONFLICT"]
    assert name_c and "同名不代表同一角色" in name_c[0]["detail"]
    assert hero["library_candidates"] == [] and hero["proposed_action"] != "review_existing_library_candidate"


def test_reference_sha_mapping_missing_and_conflicts(mig):
    orch, pid = mig
    e = _entries(analyze(pid, orch.settings.workspace))
    clean = e["clean"]
    assert clean["references"][0]["status"] == "mapped" and clean["proposed_reference_asset_ids"] == ["free_face"]
    assert len(clean["references"][0]["sha256"]) == 64
    assert e["heroine"]["references"][0]["status"] == "missing" and "REFERENCE_MISSING" in _codes(e["heroine"])
    assert e["heroine"]["references"][0]["sha256"] is None  # 不補造
    assert "REFERENCE_HASH_CONFLICT" in _codes(e["dupref"]) and e["dupref"]["classification"] == "HUMAN_REQUIRED"
    match = e["match"]
    assert "LIBRARY_MATCH_CANDIDATE" in _codes(match) and match["proposed_action"] == "review_existing_library_candidate"
    assert match["classification"] == "HUMAN_REQUIRED" and len(match["library_candidates"]) == 1  # 唯一 sha 也只是候選，需人工確認
    assert "UNKNOWN_FIELD" in _codes(clean) and clean["classification"] == "HUMAN_REQUIRED"  # 未知欄位 → 人工


def test_auto_mappable_when_everything_is_clear(orchestrator, tmp_path):
    from see.models.project import CharacterAppearance, CharacterVoice

    p = orchestrator.create_project(TINY_STORY, project_id="mig_clear")
    orchestrator.write_script(p)
    orchestrator.storyboard(p)
    p.script.characters = []
    for b in p.script.beats:
        b.character_ids = []
    for s in p.scenes:
        s.character_ids = []
    p.characters = {"a1": CharacterVoice(character_id="a1", display_name="阿光", voice_id="zm_009",
                                         appearance=CharacterAppearance(outfit_en="white shirt"))}
    p.scenes[0].character_ids = ["a1"]
    orchestrator.store.save(p)
    res = analyze("mig_clear", orchestrator.settings.workspace)
    a1 = _entries(res)["a1"]
    assert a1["classification"] == "AUTO_MAPPABLE" and a1["proposed_action"] == "create_new_library_character"
    assert a1["proposed_character_id"] == PENDING_ID and not a1["requires_human_decision"]  # 不產生真 ID
    assert res["report"]["summary"]["migration_ready"] is True


def test_scene_and_dialogue_impact_counting(mig):
    orch, pid = mig
    res = analyze(pid, orch.settings.workspace)
    e = _entries(res)
    p = orch.store.load(pid)
    s0, s1 = p.scenes[0].scene_id, p.scenes[1].scene_id
    hero = e["hero"]
    assert hero["usage_counts"]["scene_character_ids"] == 1 and hero["usage_counts"]["dialogue"] == 1
    assert hero["usage_counts"]["scene_overrides"] == 1 and hero["affected_scene_ids"] == [s0]
    assert hero["rewrite_count"] == 4  # character_ids、characters[0]、dialogue[0]、characters 鍵
    assert e["heroine"]["usage_counts"]["gaze_targets"] == 1
    nar = e["narrator"]
    assert nar["usage_counts"]["narration"] == 1 and nar["usage_counts"]["voice_overrides"] == 1
    assert {"scene_id": s0, "field": "narrator_id"} in nar["rewrites"]
    stranger = e["stranger"]
    assert stranger["source"] == "scene_reference_only" and "SCENE_REFERENCE_INCONSISTENT" in _codes(stranger)
    both = e["both"]
    assert both["affected_scene_ids"] == sorted([s0, s1])
    summ = res["report"]["summary"]
    assert summ["total_rewrite_references"] == sum(x["rewrite_count"] for x in e.values())
    assert set(summ["affected_scenes"]) >= {s0, s1} and summ["migration_ready"] is False
    assert summ["total_legacy_characters"] == len(p.characters)


def test_deterministic_report_and_input_hash(mig):
    orch, pid = mig
    ws = orch.settings.workspace
    a, b = analyze(pid, ws), analyze(pid, ws)
    assert json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)
    assert a["report"]["migration_report_schema_version"] == MIGRATION_REPORT_SCHEMA_VERSION == 1
    assert a["report"]["notice"] == "Batch 4 only analyzes. No project has been migrated."
    h = a["report"]["report_input_hash"]
    from see.storage.character_store import CharacterStore

    cid = CharacterStore(ws).list()[0].definition.character_id
    CharacterStore(ws).update(cid, notes="changed")  # Library 改變 → input hash 改變
    assert analyze(pid, ws)["report"]["report_input_hash"] != h


def test_zero_write_byte_for_byte(mig, tmp_path):
    orch, pid = mig
    ws = orch.settings.workspace

    def snap():
        return {p.relative_to(ws).as_posix(): p.read_bytes() for p in sorted(ws.rglob("*")) if p.is_file()}

    before, d0 = snap(), workspace_digest(ws)
    analyze(pid, ws)
    analyze(pid, ws)
    after = snap()
    assert after == before and workspace_digest(ws) == d0  # project.json、Library、history、.ref.json、Scene、manifest 全部不變
    assert not (ws / "backups").exists() and not (ws / "migrations").exists()
    assert orch.store.load(pid).cast == []


def test_cli_dry_run_guard_json_and_proof(mig, monkeypatch, capsys, tmp_path):
    from see.app.cli import main

    orch, pid = mig
    monkeypatch.setenv("SEE_WORKSPACE", str(orch.settings.workspace))
    assert main(["character-migrate", pid]) == 2
    assert "實際 migration 尚未核准" in capsys.readouterr().err
    assert main(["character-migrate", pid, "--dry-run", "--json"]) == 0
    env = json.loads(capsys.readouterr().out)
    assert env["migration_report_schema_version"] == 1 and env["zero_write_proof"]["unchanged"] is True and "generated_at" in env
    assert main(["character-migrate", pid, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "只分析，未遷移任何資料" in out and "zero-write：通過" in out
    assert main(["character-migrate", pid, "--dry-run", "--out", str(orch.settings.workspace / "r.json")]) == 2  # 不可寫進 workspace
    target = tmp_path / "reports" / "r.json"
    assert main(["character-migrate", pid, "--dry-run", "--json", "--out", str(target)]) == 0 and target.is_file()
    assert main(["character-migrate", pid, "--dry-run", "--json", "--out", str(target)]) == 2  # 不覆寫


def test_old_project_without_characters_and_with_cast(orchestrator):
    p = orchestrator.create_project(TINY_STORY, project_id="mig_old")
    orchestrator.write_script(p)
    orchestrator.storyboard(p)
    f = orchestrator.store.project_file("mig_old")
    raw = json.loads(f.read_text(encoding="utf-8"))
    for k in ("cast", "cast_schema_version"):
        raw.pop(k)
    f.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    res = analyze("mig_old", orchestrator.settings.workspace)
    assert res["report"]["character_binding_state"] == "v0_legacy" and res["report"]["summary"]["total_legacy_characters"] == 0
    from see.models.character_binding import CharacterBinding

    p = orchestrator.store.load("mig_old")
    p.cast = [CharacterBinding(character_id="char_aaaaaa", character_revision=1)]
    orchestrator.store.save(p)
    r2 = analyze("mig_old", orchestrator.settings.workspace)["report"]
    assert r2["character_binding_state"] == "v1_has_cast" and r2["summary"]["migration_ready"] is False


@requires_ffmpeg
def test_dry_run_does_not_change_fingerprints_or_pipeline(mig):
    orch, pid = mig
    p = orch.store.load(pid)
    orch.build_scene_assets(p)
    fps = {s.scene_id: {k: v.fingerprint for k, v in orch.store.load_manifest(pid, s.scene_id).entries.items()} for s in p.scenes}
    analyze(pid, orch.settings.workspace)
    reps = orch.build_scene_assets(orch.store.load(pid))
    assert all(r.rebuilt == [] for r in reps)
    assert {s.scene_id: {k: v.fingerprint for k, v in orch.store.load_manifest(pid, s.scene_id).entries.items()} for s in p.scenes} == fps
