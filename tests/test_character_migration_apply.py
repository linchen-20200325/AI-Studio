"""D-071 Batch 5：character-migrate --apply／--rollback（合成專案；不碰任何真實專案）。
"""
from __future__ import annotations

import json
import re

import pytest

from see.core import character_migration_apply as cma
from see.core import migration_decisions as md
from see.core.character_migration import analyze
from see.models.script import Character
from see.storage.character_store import CharacterStore
from tests.conftest import TINY_STORY, requires_ffmpeg

PID = "sd15like"
SCRIPT_ONLY = {"char_01": "阿光", "char_02": "小雨", "char_03": "老王", "char_04": "店長"}
NEW_ID = re.compile(r"^char_[0-9a-f]{12}$")


@pytest.fixture
def proj(orchestrator):
    """sd15test 形狀：Project.characters 為空、四個 SCRIPT_ONLY 角色、Scene／beat／對白／SceneCharacter／視線引用。"""
    from see.models.scene import Dialogue
    from see.models.scene_character import SceneCharacter

    p = orchestrator.create_project(TINY_STORY, project_id=PID)
    orchestrator.write_script(p)
    orchestrator.storyboard(p)
    p.characters = {}
    p.script.characters = [Character(character_id=c, name=n, description="", visual_prompt="") for c, n in SCRIPT_ONLY.items()]
    ids = list(SCRIPT_ONLY)
    for i, s in enumerate(p.scenes):
        s.character_ids = [ids[i % 4], ids[(i + 1) % 4]]
    s0 = p.scenes[0]
    s0.characters = [SceneCharacter(character_id=s0.character_ids[0],
                                    gaze={"preset": "at_character", "target_character_id": s0.character_ids[1]})]
    s0.dialogue = [Dialogue(character_id=s0.character_ids[0], text="走吧")]
    p.script.beats[0].character_ids = ["char_03"]
    orchestrator.store.save(p)
    return orchestrator


def _decide(orch, tmp_path, actions=None, name="decisions.json"):
    ws = orch.settings.workspace
    base = analyze(PID, ws)
    doc = md.decisions_template(base)
    doc["decisions"] = [{"legacy_id": c, "action": "create_new"} for c in SCRIPT_ONLY] if actions is None else actions
    f = tmp_path / name
    f.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    d, errs, dsha = md.load_decisions(f)
    res = md.apply_decisions(base, d, CharacterStore(ws), load_errors=errs, decisions_file_sha256=dsha)
    return f, res["report"]["summary"].get("apply_confirmation_token"), res


def _snap(ws):
    return {p.relative_to(ws).as_posix(): p.read_bytes() for p in sorted(ws.rglob("*")) if p.is_file()}


def _core(ws):
    """「production 可見」狀態：projects／character_library／reference_library（不含 backups、migrations 稽核紀錄）。"""
    return {k: v for k, v in _snap(ws).items() if k.split("/")[0] in ("projects", "character_library", "reference_library")}


def test_happy_path_four_create_new(proj, tmp_path):
    orch = proj
    ws = orch.settings.workspace
    f, token, res = _decide(orch, tmp_path)
    planned = res["report"]["summary"]["planned_rewrite_references"]
    assert token and len(token) == 12 and planned == len(res["report"]["proposed_rewrite_plan"]) > 0
    before = orch.store.project_file(PID).read_bytes()
    rec = cma.apply(PID, ws, f, token)
    assert rec["status"] == "committed" and rec["rewrite_count"] == planned  # 不 hard-code；等於 reviewed plan
    p = orch.store.load(PID)
    m = {x["legacy_id"]: x["character_id"] for x in rec["legacy_to_library"]}
    assert set(m) == set(SCRIPT_ONLY) and len(set(m.values())) == 4 and all(NEW_ID.match(v) for v in m.values())
    assert sorted(b.character_id for b in p.cast) == sorted(m.values())
    assert all(b.character_revision == 1 and b.follow == "pinned" for b in p.cast)
    cs = CharacterStore(ws)
    for lid, cid in m.items():
        rev = cs.read_revision(cid, 1)
        assert rev.definition.display_name == SCRIPT_ONLY[lid] and rev.definition.gender_presentation.value == "unspecified"
        assert rev.provenance["migration_id"] == rec["migration_id"] and rev.provenance["legacy_id"] == lid
    text = json.dumps(json.loads(orch.store.project_file(PID).read_text(encoding="utf-8")), ensure_ascii=False)
    for lid in SCRIPT_ONLY:
        assert f'"{lid}"' not in text  # 0 個 planned legacy reference 殘留
    assert [c.name for c in p.script.characters] == list(SCRIPT_ONLY.values())  # 劇本資料保留
    bdir = ws / rec["backup_path"]
    man = cma.verify_backup(bdir)
    assert (bdir / "project.json").read_bytes() == before and man["plan_sha256"] == rec["plan_sha256"]
    assert man["decisions_file_sha256"] == rec["decisions_file_sha256"]
    log = json.loads((cma.migrations_dir(ws, PID) / f"{rec['migration_id']}.json").read_text(encoding="utf-8"))
    assert log["status"] == "committed" and log["migrated_project_sha256"] == cma._bsha(orch.store.project_file(PID).read_bytes())
    assert not list(cma.migrations_dir(ws, PID).glob("*.staging")) and not (cma.migrations_dir(ws, PID) / ".lock").exists()
    # production 仍不以 cast 為來源：pipeline 的 image request 不讀 cast
    req, _ = orch.image_request(p, p.scenes[0])
    assert "characters" not in req.params


def test_idempotent_refuses_second_apply(proj, tmp_path):
    ws = proj.settings.workspace
    f, token, _ = _decide(proj, tmp_path)
    cma.apply(PID, ws, f, token)
    n = len(CharacterStore(ws).list(include_archived=True))
    with pytest.raises(cma.MigrationError) as e:
        cma.apply(PID, ws, f, token)
    assert e.value.code in ("PROJECT_ALREADY_HAS_CAST", "DECISIONS_STALE", "ALREADY_MIGRATED")
    assert len(CharacterStore(ws).list(include_archived=True)) == n  # 沒有第二組 ID


@pytest.mark.parametrize("confirm", [None, "", "000000000000"])
def test_confirmation_token_required(proj, tmp_path, confirm):
    ws = proj.settings.workspace
    f, _, _ = _decide(proj, tmp_path)
    before = _snap(ws)
    with pytest.raises(cma.MigrationError) as e:
        cma.apply(PID, ws, f, confirm)
    assert e.value.code == "CONFIRMATION_REQUIRED" and _snap(ws) == before


def _expect_no_write(ws, fn, code):
    before = _snap(ws)
    with pytest.raises(cma.MigrationError) as e:
        fn()
    assert e.value.code == code, e.value
    assert _snap(ws) == before  # preflight 失敗 → 一個 byte 都不寫


def test_preflight_fail_closed_cases(proj, tmp_path):
    orch = proj
    ws = orch.settings.workspace
    f, token, _ = _decide(orch, tmp_path)
    # project modified after dry-run → stale
    p = orch.store.load(PID)
    p.scenes[0].narration = p.scenes[0].narration + "。"
    orch.store.save(p)
    _expect_no_write(ws, lambda: cma.apply(PID, ws, f, token), "DECISIONS_STALE")


def test_library_modified_after_dry_run_is_stale(proj, tmp_path):
    ws = proj.settings.workspace
    f, token, _ = _decide(proj, tmp_path)
    CharacterStore(ws).create_new(display_name="路人")
    _expect_no_write(ws, lambda: cma.apply(PID, ws, f, token), "DECISIONS_STALE")


def test_not_ready_and_rejected_decisions(proj, tmp_path):
    ws = proj.settings.workspace
    f, token, res = _decide(proj, tmp_path, actions=[{"legacy_id": "char_01", "action": "create_new"}])
    assert token is None and res["report"]["summary"]["migration_ready"] is False
    _expect_no_write(ws, lambda: cma.apply(PID, ws, f, "abcdef123456"), "NOT_MIGRATION_READY")
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    _expect_no_write(ws, lambda: cma.apply(PID, ws, bad, "abcdef123456"), "DECISIONS_REJECTED")


def test_missing_revision_and_reference_integrity(proj, tmp_path):
    from PIL import Image

    from see.core.reference_library import ReferenceLibrary
    from see.models.character_definition import RefRole

    ws = proj.settings.workspace
    cs = CharacterStore(ws)
    cid = cs.create_new(display_name="其他").definition.character_id
    f, token, _ = _decide(proj, tmp_path)
    (cs.root / "history" / cid / "r000001.json").write_text("{}", encoding="utf-8")  # revision 被竄改
    _expect_no_write(ws, lambda: cma.apply(PID, ws, f, token), "CHARACTER_LIBRARY_INTEGRITY")
    cs2 = tmp_path  # 第二情境：reference hash mismatch
    (cs.root / "history" / cid).rename(cs2 / "moved_history")
    (cs.root / f"{cid}.json").rename(cs2 / "moved_head.json")
    img = ws / "reference_library" / "people" / "x.png"
    img.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), (1, 2, 3)).save(img)
    ReferenceLibrary(ws).register("people/x.png", asset_id="x", role=RefRole.identity_face, source_type="user_supplied")
    Image.new("RGB", (8, 8), (9, 9, 9)).save(img)  # 登記後內容被改
    f2, token2, _ = _decide(proj, tmp_path, name="d2.json")
    _expect_no_write(ws, lambda: cma.apply(PID, ws, f2, token2 or "x" * 12), "REFERENCE_LIBRARY_INTEGRITY")


def test_project_already_has_cast(proj, tmp_path):
    from see.models.character_binding import CharacterBinding

    ws = proj.settings.workspace
    p = proj.store.load(PID)
    p.cast = [CharacterBinding(character_id="char_aaaaaaaaaaaa", character_revision=1)]
    proj.store.save(p)
    f, _, _ = _decide(proj, tmp_path)
    _expect_no_write(ws, lambda: cma.apply(PID, ws, f, "abcdef123456"), "PROJECT_ALREADY_HAS_CAST")


def test_rewrite_location_changed_and_count_mismatch():
    raw = {"scenes": [{"scene_id": "s1", "character_ids": ["char_01", "x"]}], "script": {"characters": [], "beats": []}}
    plan = [{"legacy_id": "char_01", "scene_id": "s1", "field": "character_ids[1]"}]
    with pytest.raises(cma.MigrationError) as e:
        cma.stage_project(raw, plan, {"char_01": "char_aaaaaaaaaaaa"}, [])
    assert e.value.code == "REWRITE_LOCATION_CHANGED"
    with pytest.raises(cma.MigrationError) as e:
        cma.stage_project(raw, [{"legacy_id": "char_01", "scene_id": "s9", "field": "character_ids[0]"}], {"char_01": "c"}, [])
    assert e.value.code == "REWRITE_LOCATION_MISSING"
    staged, n = cma.stage_project(raw, [{"legacy_id": "char_01", "scene_id": "s1", "field": "character_ids[0]"}],
                                  {"char_01": "char_aaaaaaaaaaaa"}, [])
    assert n == 1 and staged["scenes"][0]["character_ids"] == ["char_aaaaaaaaaaaa", "x"] and raw["scenes"][0]["character_ids"][0] == "char_01"


def _assert_restored(orch, ws, before_core, before_project, created_must_be_archived=True):
    assert orch.store.project_file(PID).read_bytes() == before_project
    assert orch.store.load(PID).cast == []
    after = _core(ws)
    new_lib = {k for k in after if k not in before_core}
    for k, v in before_core.items():
        assert after.get(k) == v, k  # 原有檔案 byte 不變
    if created_must_be_archived:
        cs = CharacterStore(ws)
        for rec in cs.list(include_archived=True):
            assert rec.archived  # 只剩封存的 migration-created 角色（不 hard delete、不可再被綁定）
    else:
        assert not new_lib
    assert not list(cma.migrations_dir(ws, PID).glob("*.staging")) and not (cma.migrations_dir(ws, PID) / ".lock").exists()
    recs = cma.list_records(ws, PID)
    assert recs and recs[-1]["status"] == "failed" and recs[-1]["project_matches_original"] is True


def test_backup_failure_writes_nothing(proj, tmp_path):
    ws = proj.settings.workspace
    f, token, _ = _decide(proj, tmp_path)
    core, pb = _core(ws), proj.store.project_file(PID).read_bytes()

    def boom(ctx, mid):
        raise OSError("disk full")

    with pytest.raises(cma.MigrationError) as e:
        cma.apply(PID, ws, f, token, _hooks={"backup": boom})
    assert e.value.code == "BACKUP_FAILED"
    assert _core(ws) == core and proj.store.project_file(PID).read_bytes() == pb
    assert not (ws / "backups" / "character_migrations" / PID).exists() or \
        not any((ws / "backups" / "character_migrations" / PID).iterdir())


def test_duplicate_generated_id_collision(proj, tmp_path, monkeypatch):
    from see.storage import character_store as csm

    ws = proj.settings.workspace
    taken = CharacterStore(ws).create_new(display_name="既有").definition.character_id
    f, token, _ = _decide(proj, tmp_path)
    core, pb = _core(ws), proj.store.project_file(PID).read_bytes()
    monkeypatch.setattr(csm, "new_character_id", lambda: taken)
    with pytest.raises(cma.MigrationError) as e:
        cma.apply(PID, ws, f, token)
    assert e.value.code == "ID_ALLOCATION_FAILED"
    assert _core(ws) == core and proj.store.project_file(PID).read_bytes() == pb


def test_staged_write_failure_rolls_back(proj, tmp_path):
    ws = proj.settings.workspace
    f, token, _ = _decide(proj, tmp_path)
    core, pb = _core(ws), proj.store.project_file(PID).read_bytes()

    def boom(ctx, text):
        raise OSError("write failed")

    with pytest.raises(cma.MigrationError) as e:
        cma.apply(PID, ws, f, token, _hooks={"commit_project": boom})
    assert e.value.code == "APPLY_FAILED"
    _assert_restored(proj, ws, core, pb)


def test_staged_project_validation_failure(proj, tmp_path):
    ws = proj.settings.workspace
    f, token, _ = _decide(proj, tmp_path)
    core, pb = _core(ws), proj.store.project_file(PID).read_bytes()

    def short(raw, plan, id_map, cast):
        staged, n = cma.stage_project(raw, plan, id_map, cast)
        return staged, n - 1

    with pytest.raises(cma.MigrationError) as e:
        cma.apply(PID, ws, f, token, _hooks={"stage_project": short})
    assert e.value.code == "REWRITE_COUNT_MISMATCH"
    _assert_restored(proj, ws, core, pb, created_must_be_archived=False)  # 尚未提交 Library → 不留下任何角色


def test_post_verify_failure_auto_rollback(proj, tmp_path):
    ws = proj.settings.workspace
    f, token, _ = _decide(proj, tmp_path)
    core, pb = _core(ws), proj.store.project_file(PID).read_bytes()
    with pytest.raises(cma.MigrationError) as e:
        cma.apply(PID, ws, f, token, _hooks={"post_verify": lambda *a: ["simulated"]})
    assert e.value.code == "POST_VERIFY_FAILED"
    _assert_restored(proj, ws, core, pb)
    # 失敗紀錄不阻擋重試。封存的 migration-created 角色仍在 Library（同名）→ NAME_CONFLICT：重試必須明確給 display_name
    _, t_plain, _ = _decide(proj, tmp_path, name="d1.json")
    assert t_plain is None
    acts = [{"legacy_id": c, "action": "create_new", "display_name": n} for c, n in SCRIPT_ONLY.items()]
    f2, token2, _ = _decide(proj, tmp_path, actions=acts, name="d2.json")
    assert token2 is not None
    rec = cma.apply(PID, ws, f2, token2)
    assert rec["status"] == "committed"


def test_rollback_restores_and_is_idempotent(proj, tmp_path):
    ws = proj.settings.workspace
    f, token, _ = _decide(proj, tmp_path)
    pb = proj.store.project_file(PID).read_bytes()
    rec = cma.apply(PID, ws, f, token)
    new_ids = [c["character_id"] for c in rec["created_characters"]]
    rb = cma.rollback(PID, ws, rec["migration_id"])
    assert rb["status"] == "rolled_back" and proj.store.project_file(PID).read_bytes() == pb
    cs = CharacterStore(ws)
    for cid in new_ids:
        assert cs.get(cid).archived and cs.read_revision(cid, 1)  # 不 hard delete；history 保留
    assert set(rb["migration_created_characters"].values()) == {"archived_by_rollback"}
    with pytest.raises(cma.MigrationError) as e:
        cma.rollback(PID, ws, rec["migration_id"])
    assert e.value.code == "ALREADY_ROLLED_BACK"
    with pytest.raises(cma.MigrationError) as e:
        cma.rollback(PID, ws, "mig_nope")
    assert e.value.code == "MIGRATION_NOT_FOUND"


def test_rollback_refused_when_project_edited_after_migration(proj, tmp_path):
    ws = proj.settings.workspace
    f, token, _ = _decide(proj, tmp_path)
    rec = cma.apply(PID, ws, f, token)
    p = proj.store.load(PID)
    p.scenes[0].narration += "（改）"
    proj.store.save(p)
    edited = proj.store.project_file(PID).read_bytes()
    with pytest.raises(cma.MigrationError) as e:
        cma.rollback(PID, ws, rec["migration_id"])
    assert e.value.code == "PROJECT_MODIFIED_AFTER_MIGRATION" and proj.store.project_file(PID).read_bytes() == edited


def test_rollback_keeps_character_used_by_other_project(proj, tmp_path):
    from see.models.character_binding import CharacterBinding

    ws = proj.settings.workspace
    f, token, _ = _decide(proj, tmp_path)
    rec = cma.apply(PID, ws, f, token)
    shared = rec["created_characters"][0]["character_id"]
    other = proj.create_project(TINY_STORY, project_id="other")
    other.cast = [CharacterBinding(character_id=shared, character_revision=1)]
    proj.store.save(other)
    rb = cma.rollback(PID, ws, rec["migration_id"])
    assert rb["migration_created_characters"][shared] == "kept_active_used_by_other_project"
    assert not CharacterStore(ws).get(shared).archived


def test_bind_existing_pins_revision(proj, tmp_path):
    ws = proj.settings.workspace
    cs = CharacterStore(ws)
    lib = cs.create_new(display_name="阿光").definition.character_id
    cs.update(lib, notes="v2")
    acts = [{"legacy_id": "char_01", "action": "bind_existing", "library_character_id": lib, "library_revision": 1}]
    acts += [{"legacy_id": c, "action": "create_new"} for c in ("char_02", "char_03", "char_04")]
    f, token, _ = _decide(proj, tmp_path, actions=acts)
    rec = cma.apply(PID, ws, f, token)
    p = proj.store.load(PID)
    b = next(x for x in p.cast if x.character_id == lib)
    assert b.character_revision == 1 and len(p.cast) == 4  # pinned r1，不是 latest r2
    assert lib not in [c["character_id"] for c in rec["created_characters"]]


def test_cli_apply_list_rollback(proj, tmp_path, monkeypatch, capsys):
    from see.app.cli import main

    ws = proj.settings.workspace
    monkeypatch.setenv("SEE_WORKSPACE", str(ws))
    f, token, _ = _decide(proj, tmp_path)
    assert main(["character-migrate", PID, "--apply", "--dry-run"]) == 2
    assert main(["character-migrate", PID, "--apply", "--confirm", token]) == 2  # 缺 --decisions
    assert main(["character-migrate", PID, "--apply", "--decisions", str(f)]) == 5  # 缺 confirm
    capsys.readouterr()
    assert main(["character-migrate", PID, "--dry-run", "--decisions", str(f)]) == 0
    assert f"apply_confirmation_token：{token}" in capsys.readouterr().out
    assert main(["character-migrate", PID, "--apply", "--decisions", str(f), "--confirm", token]) == 0
    out = capsys.readouterr().out
    mid = re.search(r"--rollback (mig_\S+)", out).group(1)
    assert main(["character-migrate", PID, "--list-migrations"]) == 0 and "status=committed" in capsys.readouterr().out
    assert main(["character-migrate", PID, "--rollback", mid]) == 0
    assert main(["character-migrate", PID, "--rollback", mid]) == 5


@requires_ffmpeg
def test_migration_keeps_fingerprints(proj, tmp_path):
    """script-only 角色沒有 Project.characters 外觀 → 改寫 ID 不影響 image／clip／narration fingerprint（production 不讀 cast）。"""
    orch = proj
    ws = orch.settings.workspace
    p = orch.store.load(PID)
    orch.build_scene_assets(p)
    fps = {s.scene_id: {k: v.fingerprint for k, v in orch.store.load_manifest(PID, s.scene_id).entries.items()} for s in p.scenes}
    f, token, _ = _decide(orch, tmp_path)
    cma.apply(PID, ws, f, token)
    reps = orch.build_scene_assets(orch.store.load(PID))
    assert all(r.rebuilt == [] for r in reps)
    assert {s.scene_id: {k: v.fingerprint for k, v in orch.store.load_manifest(PID, s.scene_id).entries.items()} for s in p.scenes} == fps


def test_crlf_project_bytes_restored_exactly(proj, tmp_path):
    """Windows 存檔可能是 CRLF：rollback／自動恢復必須回到原始 bytes（binary 寫入，不做換行轉換）。"""
    ws = proj.settings.workspace
    pf = proj.store.project_file(PID)
    crlf = pf.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    pf.write_bytes(crlf)
    f, token, _ = _decide(proj, tmp_path)
    with pytest.raises(cma.MigrationError):
        cma.apply(PID, ws, f, token, _hooks={"post_verify": lambda *a: ["simulated"]})
    assert pf.read_bytes() == crlf
    acts = [{"legacy_id": c, "action": "create_new", "display_name": n} for c, n in SCRIPT_ONLY.items()]
    f2, token2, _ = _decide(proj, tmp_path, actions=acts, name="d2.json")
    rec = cma.apply(PID, ws, f2, token2)
    cma.rollback(PID, ws, rec["migration_id"])
    assert pf.read_bytes() == crlf
