"""D-070 Batch 4.1：Migration Human Decisions Layer。Batch 4.1 remains analysis-only. No project has been migrated."""
from __future__ import annotations

import copy
import json
import re

import pytest

from see.core import migration_decisions as md
from see.core.character_migration import PENDING_ID, analyze, workspace_digest
from see.models.script import Character
from see.storage.character_store import CharacterStore
from tests import migration_fixture as fx
from tests.conftest import TINY_STORY

SCRIPT_ONLY = {"char_01": "阿光", "char_02": "小雨", "char_03": "老王", "char_04": "店長"}


@pytest.fixture
def sd15like(orchestrator):
    """模擬真機 sd15test 形狀：Project.characters 為空，四個只存在劇本／Scene 的角色（全部 SCRIPT_ONLY_CHARACTER）。"""
    p = orchestrator.create_project(TINY_STORY, project_id="sd15like")
    orchestrator.write_script(p)
    orchestrator.storyboard(p)
    p.characters = {}
    p.script.characters = [Character(character_id=c, name=n, description="", visual_prompt="") for c, n in SCRIPT_ONLY.items()]
    ids = list(SCRIPT_ONLY)
    for i, s in enumerate(p.scenes):
        s.character_ids = [ids[i % 4], ids[(i + 1) % 4]]
    orchestrator.store.save(p)
    return orchestrator, "sd15like"


def _doc(base, decisions, **over):
    d = md.decisions_template(base)
    d["decisions"] = decisions
    d.update(over)
    return d


def _run(orch, pid, doc):
    ws = orch.settings.workspace
    base = analyze(pid, ws)
    return base, md.apply_decisions(base, doc, CharacterStore(ws))


def _by_id(res):
    return {e["legacy_id"]: e for e in res["report"]["entries"]}


def _codes(res):
    return [e["code"] for e in res["report"]["decisions"]["errors"]]


def test_script_only_without_decision_stays_blocking(sd15like):
    orch, pid = sd15like
    base = analyze(pid, orch.settings.workspace)
    s = base["report"]["summary"]
    assert s["human_required"] == 4 and s["migration_ready"] is False and s["total_legacy_characters"] == 0
    tpl = md.decisions_template(base)
    assert [d["legacy_id"] for d in tpl["decisions"]] == list(SCRIPT_ONLY) and all(d["action"] is None for d in tpl["decisions"])
    res = md.apply_decisions(base, tpl, CharacterStore(orch.settings.workspace))  # 範本未填 → fail closed
    assert res["report"]["summary"]["migration_ready"] is False and res["report"]["decisions"]["status"] == "rejected"
    assert set(_codes(res)) == {"DECISION_INVALID_ACTION"}
    assert all(e["decision_outcome"] == "UNRESOLVED" and e["remaining_blocking_conflicts"] == ["SCRIPT_ONLY_CHARACTER"]
               for e in res["report"]["entries"])
    partial = _doc(base, [{"legacy_id": "char_01", "action": "create_new"}])  # 只決定一個：其餘仍 blocking
    r2 = md.apply_decisions(base, partial, CharacterStore(orch.settings.workspace))
    assert r2["report"]["decisions"]["status"] == "applied" and r2["report"]["summary"]["migration_ready"] is False
    assert r2["report"]["summary"]["unresolved_entries"] == 3


def test_all_create_new_makes_ready_for_planning_only(sd15like):
    orch, pid = sd15like
    base = analyze(pid, orch.settings.workspace)
    base_copy = copy.deepcopy(base)
    res = md.apply_decisions(base, _doc(base, [{"legacy_id": c, "action": "create_new"} for c in SCRIPT_ONLY]),
                             CharacterStore(orch.settings.workspace))
    assert base == base_copy  # 基礎報告不被修改
    r, s = res["report"], res["report"]["summary"]
    assert s["migration_ready"] is True and s["decisions_status"] == "applied" and s["blocking_conflicts"] == 0
    assert "不代表已遷移" in s["migration_ready_scope"] and "Batch 5" in s["migration_ready_scope"]
    assert r["notice"] == "Batch 4.1 remains analysis-only. No project has been migrated."
    assert r["kind"] == "character_migration_dry_run_with_decisions" and r["base_summary"]["migration_ready"] is False
    assert s["new_character_placeholders"] == 4 and s["planned_rewrite_references"] == base["report"]["summary"]["total_rewrite_references"]
    assert {w["target"] for w in r["proposed_rewrite_plan"]} == {PENDING_ID}
    for e in r["entries"]:
        assert e["decision"]["proposed_character_id"] == PENDING_ID and e["resolved_conflicts"] == ["SCRIPT_ONLY_CHARACTER"]
        assert e["decision"]["display_name"] == SCRIPT_ONLY[e["legacy_id"]]
    assert not re.search(r"char_[0-9a-f]{12}", json.dumps(r, ensure_ascii=False))  # 沒有產生正式 Library ID
    assert CharacterStore(orch.settings.workspace).list(include_archived=True) == []  # 沒有建立 CharacterDefinition


def test_stale_decisions_fail_closed(sd15like):
    orch, pid = sd15like
    ws = orch.settings.workspace
    base = analyze(pid, ws)
    doc = _doc(base, [{"legacy_id": c, "action": "create_new"} for c in SCRIPT_ONLY])
    p = orch.store.load(pid)
    p.scenes[0].character_ids = ["char_01"]  # 專案在決定後被改動
    orch.store.save(p)
    res = md.apply_decisions(analyze(pid, ws), doc, CharacterStore(ws))
    assert res["report"]["decisions"]["status"] == "stale" and res["report"]["summary"]["migration_ready"] is False
    assert "DECISIONS_STALE" in _codes(res) and res["report"]["decisions"]["accepted"] == []
    assert all(e["decision"] is None for e in res["report"]["entries"])
    base2 = analyze(pid, ws)
    bad_sha = _doc(base2, doc["decisions"], source_report_sha256="0" * 64)
    assert md.apply_decisions(base2, bad_sha, CharacterStore(ws))["report"]["decisions"]["status"] == "stale"


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d.update(extra=1), "DECISIONS_UNKNOWN_FIELD"),
    (lambda d: d.update(migration_decisions_schema_version=2), "DECISIONS_SCHEMA_UNSUPPORTED"),
    (lambda d: d.update(kind="x"), "DECISIONS_KIND_INVALID"),
    (lambda d: d.update(project_id="other"), "DECISIONS_PROJECT_MISMATCH"),
    (lambda d: d.pop("source_report_input_hash"), "DECISIONS_SCHEMA_INVALID"),
    (lambda d: d["decisions"].append({"legacy_id": "char_01", "action": "create_new"}), "DECISION_DUPLICATE"),
    (lambda d: d["decisions"].append({"legacy_id": "nobody", "action": "create_new"}), "DECISION_UNKNOWN_LEGACY_ID"),
    (lambda d: d["decisions"][0].update(character_id="char_abc"), "DECISION_FIELD_NOT_ALLOWED"),  # 不可自訂正式 ID
    (lambda d: d["decisions"][0].update(action="merge"), "DECISION_INVALID_ACTION"),
    (lambda d: d["decisions"][0].update(action="keep_legacy"), "DECISION_ACTION_NOT_APPLICABLE"),  # 無 legacy 資料
    (lambda d: d["decisions"][0].update(action="ignore_unused"), "DECISION_ACTION_NOT_APPLICABLE"),  # 有 Scene 引用
    (lambda d: d["decisions"][0].update(action="narrator_setting"), "DECISION_ACTION_NOT_APPLICABLE"),
    (lambda d: d["decisions"][0].update(display_name="  "), "DECISION_FIELD_INVALID"),
    (lambda d: d["decisions"][0].update(action="bind_existing"), "DECISION_FIELD_REQUIRED"),
])
def test_validation_errors_reject_whole_file(sd15like, mutate, code):
    orch, pid = sd15like
    base = analyze(pid, orch.settings.workspace)
    doc = _doc(base, [{"legacy_id": c, "action": "create_new"} for c in SCRIPT_ONLY])
    mutate(doc)
    res = md.apply_decisions(base, doc, CharacterStore(orch.settings.workspace))
    assert code in _codes(res) and res["report"]["decisions"]["status"] == "rejected"
    assert res["report"]["summary"]["migration_ready"] is False and res["report"]["decisions"]["accepted"] == []  # all-or-nothing


def test_invalid_json_and_non_object(sd15like, tmp_path):
    orch, pid = sd15like
    base = analyze(pid, orch.settings.workspace)
    f = tmp_path / "d.json"
    f.write_text("{not json", encoding="utf-8")
    doc, errs, dsha = md.load_decisions(f)
    res = md.apply_decisions(base, doc, CharacterStore(orch.settings.workspace), load_errors=errs, decisions_file_sha256=dsha)
    assert _codes(res) == ["DECISIONS_INVALID_JSON"] and res["report"]["decisions"]["decisions_file_sha256"] == dsha
    assert md.apply_decisions(base, [], CharacterStore(orch.settings.workspace))["report"]["decisions"]["status"] == "rejected"


def test_bind_existing_pinned_revision(sd15like):
    orch, pid = sd15like
    ws = orch.settings.workspace
    cs = CharacterStore(ws)
    cid = cs.create_new(display_name="阿光").definition.character_id
    cs.update(cid, notes="v2")
    gone = cs.create_new(display_name="舊角").definition.character_id
    cs.archive(gone)
    base = analyze(pid, ws)
    decs = [{"legacy_id": "char_01", "action": "bind_existing", "library_character_id": cid, "library_revision": 1}]
    decs += [{"legacy_id": c, "action": "create_new"} for c in ("char_02", "char_03", "char_04")]
    res = md.apply_decisions(base, _doc(base, decs), cs)
    e = _by_id(res)["char_01"]
    assert res["report"]["summary"]["migration_ready"] is True
    assert e["decision"]["library_revision"] == 1 and len(e["decision"]["library_revision_content_sha256"]) == 64  # pinned，非 latest
    assert {w["target_kind"] for w in res["report"]["proposed_rewrite_plan"] if w["legacy_id"] == "char_01"} == \
        {"existing_library_character_pinned"}
    assert {"NAME_CONFLICT", "SCRIPT_ONLY_CHARACTER"} <= set(e["resolved_conflicts"]) and e["remaining_blocking_conflicts"] == []
    for bad, code in (({"library_revision": 9}, "DECISION_LIBRARY_REVISION_NOT_FOUND"),
                      ({"library_character_id": "char_nope"}, "DECISION_LIBRARY_CHARACTER_NOT_FOUND"),
                      ({"library_character_id": gone}, "DECISION_LIBRARY_CHARACTER_ARCHIVED"),
                      ({"library_revision": 0}, "DECISION_FIELD_INVALID")):
        d2 = copy.deepcopy(decs)
        d2[0].update(bad)
        r2 = md.apply_decisions(base, _doc(base, d2), cs)
        assert code in _codes(r2) and r2["report"]["summary"]["migration_ready"] is False


def test_field_level_conflicts_not_resolved_by_create_new(orchestrator, tmp_path):
    private = tmp_path / "private_refs"
    private.mkdir()
    pid = fx.build(orchestrator, private, TINY_STORY)
    ws = orchestrator.settings.workspace
    base = analyze(pid, ws)
    cs = CharacterStore(ws)
    e = {x["legacy_id"]: x for x in base["report"]["entries"]}
    assert md.applicable_actions(e["narrator"]) == ["create_new", "bind_existing", "narrator_setting"]
    assert "keep_legacy" in md.applicable_actions(e["ghost"]) and "ignore_unused" in md.applicable_actions(e["ghost"])
    assert "narrator_setting" not in md.applicable_actions(e["both"])  # 有畫面引用
    # hero 名稱與 Library 同名 → create_new 必須明確給 display_name
    r0 = md.apply_decisions(base, _doc(base, [{"legacy_id": "hero", "action": "create_new"}]), cs)
    assert "DECISION_FIELD_REQUIRED" in _codes(r0)
    r1 = md.apply_decisions(base, _doc(base, [{"legacy_id": "hero", "action": "create_new", "display_name": "阿明（第二位）"},
                                              {"legacy_id": "ghost", "action": "keep_legacy"}]), cs)
    hero, ghost = _by_id(r1)["hero"], _by_id(r1)["ghost"]
    assert r1["report"]["decisions"]["status"] == "applied"
    assert "NAME_CONFLICT" in hero["resolved_conflicts"]
    assert {"GENDER_MAPPING_AMBIGUOUS", "AGE_MAPPING_AMBIGUOUS"} <= set(hero["remaining_blocking_conflicts"])  # 不推論性別／年齡
    assert hero["decision_outcome"] == "UNRESOLVED" and r1["report"]["summary"]["migration_ready"] is False
    assert ghost["decision_outcome"] == "RESOLVED" and ghost["planned_disposition"] == "keep_in_legacy_characters"
    assert not [w for w in r1["report"]["proposed_rewrite_plan"] if w["legacy_id"] == "ghost"]
    r2 = md.apply_decisions(base, _doc(base, [{"legacy_id": "clean", "action": "keep_legacy"}]), cs)  # 有 Scene 引用 → 不可留 legacy
    assert "DECISION_ACTION_NOT_APPLICABLE" in _codes(r2)


def test_deterministic_and_zero_write(sd15like, tmp_path):
    orch, pid = sd15like
    ws = orch.settings.workspace
    base = analyze(pid, ws)
    doc = _doc(base, [{"legacy_id": c, "action": "create_new", "note": "新角色"} for c in SCRIPT_ONLY])
    f = tmp_path / "decisions.json"
    f.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    def snap():
        return {p.relative_to(ws).as_posix(): p.read_bytes() for p in sorted(ws.rglob("*")) if p.is_file()}

    before, d0, fbytes = snap(), workspace_digest(ws), f.read_bytes()
    outs = []
    for _ in range(2):
        d, errs, dsha = md.load_decisions(f)
        outs.append(md.apply_decisions(analyze(pid, ws), d, CharacterStore(ws), load_errors=errs, decisions_file_sha256=dsha))
    assert outs[0] == outs[1] and outs[0]["report"]["summary"]["migration_ready"] is True
    assert snap() == before and workspace_digest(ws) == d0 and f.read_bytes() == fbytes
    p = orch.store.load(pid)
    assert p.cast == [] and p.characters == {} and not (ws / "backups").exists() and not (ws / "migrations").exists()


def test_cli_template_and_decisions(sd15like, monkeypatch, capsys, tmp_path):
    from see.app.cli import main

    orch, pid = sd15like
    monkeypatch.setenv("SEE_WORKSPACE", str(orch.settings.workspace))
    assert main(["character-migrate", pid, "--decisions", "x.json"]) == 2  # 仍必須 --dry-run
    capsys.readouterr()
    assert main(["character-migrate", pid, "--dry-run", "--decisions", "x", "--decisions-template"]) == 2
    capsys.readouterr()
    tpl_path = tmp_path / "decisions.json"
    assert main(["character-migrate", pid, "--dry-run", "--decisions-template", "--out", str(tpl_path)]) == 0
    capsys.readouterr()
    assert main(["character-migrate", pid, "--dry-run", "--decisions", str(tpl_path)]) == 4  # 未填 action → 不採用
    out = capsys.readouterr().out
    assert "驗證失敗（未採用）" in out and "zero-write：通過" in out and md.NOTICE in out
    doc = json.loads(tpl_path.read_text(encoding="utf-8"))
    for d in doc["decisions"]:
        d["action"] = "create_new"
    filled = tmp_path / "filled.json"
    filled.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    assert main(["character-migrate", pid, "--dry-run", "--json", "--decisions", str(filled)]) == 0
    env = json.loads(capsys.readouterr().out)
    assert env["zero_write_proof"]["unchanged"] is True and env["report"]["summary"]["migration_ready"] is True
    assert env["report"]["decisions"]["decisions_file_sha256"] and env["report_sha256"] != env["report"]["base_report_sha256"]
