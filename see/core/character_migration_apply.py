"""Character migration apply／rollback（D-071 Batch 5）：依 Batch 4.1 reviewed plan 逐專案遷移，全有或全無。

**Batch 5 engine implemented ≠ any real project migrated.** 本模組只在使用者明確執行
`character-migrate <pid> --apply --decisions <file> --confirm <token>` 時寫入；production pipeline 仍只用 `Project.characters`
（Project.cast 不是 production source of truth；Batch 6 才切換）。

流程（transaction；任一步失敗 → 不留下半套）：
1. preflight：重跑 analyze()＋apply_decisions()；決定檔 applied、migration_ready、hash 一致、confirm token＝plan hash 前 12 碼、
   Project 尚無 cast、沒有已提交的 migration、Character／Reference Library integrity、workspace／project schema 相容。
2. backup：`workspace/backups/character_migrations/<pid>/<migration_id>/`（先寫 `.partial` 再 rename；不覆寫；只含 JSON，不複製圖片）。
3. stage：新角色（create_new；系統產生 `char_`＋hex ID；revision 1；provenance 記 migration_id／legacy_id）寫進 staging；
   project.json 依 `proposed_rewrite_plan` 逐一改寫（每個位置寫入前確認仍是 legacy_id；實際改寫數必須等於計畫數），加 Project.cast（pinned）。
4. verify staged → journal（log status=committing）→ commit（新角色檔 rename 進 Library；project.json atomic replace）→ post-verify。
5. post-verify 失敗或 commit 失敗 → 自動 rollback：project.json 以 backup bytes 還原；本次新建角色 **archive（不 hard delete）**，
   provenance 留在不可變 history（D-066 §8.1）。
Rollback（`--rollback <migration_id>`）：同一筆 committed record；驗 backup hash；目前 project.json 必須仍是 migration 後的 bytes
（之後被改過 → 拒絕，避免丟失使用者修改）；新建角色若已被其他專案 cast 使用 → 保持 active（不破壞他人綁定），否則 archive。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from see.core import migration_decisions as md
from see.core.character_migration import PENDING_ID, _sha, analyze

MIGRATION_RECORD_SCHEMA_VERSION = 1
BACKUP_SCHEMA_VERSION = 1
NOTICE = "Batch 5 engine implemented ≠ any real project migrated. Project.cast is not yet production source of truth (Batch 6)."

# 狀態
COMMITTING = "committing"
COMMITTED = "committed"
ROLLED_BACK = "rolled_back"
FAILED = "failed"  # 失敗且已自動恢復（或在寫入前就停止）


class MigrationError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _bsha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def migrations_dir(ws: Path, pid: str) -> Path:
    return Path(ws) / "migrations" / pid


def backups_dir(ws: Path, pid: str) -> Path:
    return Path(ws) / "backups" / "character_migrations" / pid


def _write_atomic(path: Path, data: str | bytes) -> None:
    """binary 寫入（Windows 文字模式會把 LF 轉 CRLF，造成 bytes 驗證與還原不一致）＋ fsync ＋ os.replace。"""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data.encode("utf-8") if isinstance(data, str) else data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def list_records(ws: Path, pid: str) -> list[dict[str, Any]]:
    d = migrations_dir(ws, pid)
    out = []
    for p in sorted(d.glob("mig_*.json")) if d.is_dir() else []:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            out.append({"migration_id": p.stem, "status": "unreadable"})
    return out


# ---------------------------------------------------------------- 引用位置（只依計畫；不重新猜）
_TOKEN = re.compile(r"^([A-Za-z_]+)(?:\[(\d+)\])?$")


def _locate(raw: dict[str, Any], item: dict[str, Any]) -> tuple[Any, Any]:
    """回傳 (container, key)；container[key] 即計畫中的位置。找不到／不唯一 → MigrationError。"""
    field = item["field"]
    if "scene_id" in item:
        hits = [s for s in raw.get("scenes") or [] if isinstance(s, dict) and s.get("scene_id") == item["scene_id"]]
        if len(hits) != 1:
            raise MigrationError("REWRITE_LOCATION_MISSING", f"scene {item['scene_id']} matched {len(hits)}")
        node: Any = hits[0]
    elif field.startswith("script."):
        node = raw
    else:
        raise MigrationError("APPLY_UNSUPPORTED_IN_BATCH5", f"{field}：Project.characters 鍵改寫（legacy 角色設定的處置）尚無規格")
    parts = field.split(".")
    for n, part in enumerate(parts):
        m = _TOKEN.match(part)
        if not m:
            raise MigrationError("REWRITE_LOCATION_MISSING", field)
        name, idx = m.group(1), m.group(2)
        last = n == len(parts) - 1
        if not isinstance(node, dict) or name not in node:
            raise MigrationError("REWRITE_LOCATION_MISSING", field)
        if idx is None:
            if last:
                return node, name
            node = node[name]
            continue
        seq = node[name]
        if not isinstance(seq, list):
            raise MigrationError("REWRITE_LOCATION_MISSING", field)
        i = int(idx)
        if name == "beats" and n > 0 and parts[n - 1] == "script":  # Beat 以 index 欄位定位（Batch 4 規則）
            beat_hits = [k for k, b in enumerate(seq) if isinstance(b, dict) and b.get("index") == i]
            if len(beat_hits) != 1:
                raise MigrationError("REWRITE_LOCATION_MISSING", f"{field}: beat index {i} matched {len(beat_hits)}")
            i = beat_hits[0]
        if not 0 <= i < len(seq):
            raise MigrationError("REWRITE_LOCATION_MISSING", field)
        if last:
            return seq, i
        node = seq[i]
    raise MigrationError("REWRITE_LOCATION_MISSING", field)


def _mask(raw: dict[str, Any], plan: list[dict[str, Any]]) -> dict[str, Any]:
    """unrelated-field 快照：把計畫位置換成固定記號、移除 cast 欄位；其餘必須在 migration 前後完全相同。"""
    import copy

    m = copy.deepcopy(raw)
    for it in plan:
        c, k = _locate(m, it)
        c[k] = "<planned_rewrite>"
    m.pop("cast", None)
    m.pop("cast_schema_version", None)
    return m


def stage_project(raw: dict[str, Any], plan: list[dict[str, Any]], id_map: dict[str, str],
                  cast: list[dict[str, Any]]) -> tuple[dict[str, Any], int]:
    """依計畫改寫（只改計畫位置；每個位置必須仍等於 legacy_id）。回傳 (staged_raw, rewrite_count)。"""
    import copy

    staged = copy.deepcopy(raw)
    count = 0
    for it in plan:
        c, k = _locate(staged, it)
        if c[k] != it["legacy_id"]:
            raise MigrationError("REWRITE_LOCATION_CHANGED", f"{it.get('scene_id', '')} {it['field']}: {c[k]!r} ≠ {it['legacy_id']!r}")
        c[k] = id_map[it["legacy_id"]]
        count += 1
    if count != len(plan):
        raise MigrationError("REWRITE_COUNT_MISMATCH", f"{count} ≠ {len(plan)}")
    staged["cast"] = cast
    staged["cast_schema_version"] = 1
    return staged, count


# ---------------------------------------------------------------- preflight（唯讀）
def preflight(project_id: str, ws: Path, decisions_path: Path, confirm: str | None) -> dict[str, Any]:
    """所有 apply 前條件；任何一項不符 → MigrationError（尚未寫任何檔）。回傳 plan context。"""
    from see.core.environment import WORKSPACE_SCHEMA_VERSION, read_workspace_version
    from see.core.reference_library import ReferenceLibrary, ReferenceLibraryError
    from see.models.project import Project
    from see.storage.character_store import CHARACTER_SCHEMA_VERSION, CharacterStore, CharacterStoreError

    ws = Path(ws)
    try:
        ver, _ = read_workspace_version(ws)
    except ValueError as e:
        raise MigrationError("WORKSPACE_SCHEMA_INCOMPATIBLE", str(e)) from e
    if ver is None or ver > WORKSPACE_SCHEMA_VERSION:
        raise MigrationError("WORKSPACE_SCHEMA_INCOMPATIBLE", f"workspace v{ver}")
    from see.storage.project_store import ProjectStore

    pfile = ProjectStore(ws).project_file(project_id)
    if not pfile.is_file():
        raise MigrationError("PROJECT_NOT_FOUND", project_id)
    project_bytes = pfile.read_bytes()
    try:
        raw = json.loads(project_bytes.decode("utf-8"))
        project = Project.model_validate(raw)
    except ValueError as e:
        raise MigrationError("PROJECT_SCHEMA_INCOMPATIBLE", str(e)) from e
    if project.cast or raw.get("cast_schema_version") is not None:
        raise MigrationError("PROJECT_ALREADY_HAS_CAST", "Project.cast 已存在：不可重複遷移")
    for r in list_records(ws, project_id):
        if r.get("status") in (COMMITTED, COMMITTING, "unreadable"):
            raise MigrationError("ALREADY_MIGRATED" if r.get("status") == COMMITTED else "INCOMPLETE_MIGRATION_RECORD",
                                 f"{r.get('migration_id')} status={r.get('status')}"
                                 + ("" if r.get("status") == COMMITTED else "；請先 --rollback 該筆"))
    # Character Library integrity（含 history hash）
    cs = CharacterStore(ws)
    plan_heads = cs.migration_plan()
    if plan_heads["newer_than_supported"] or plan_heads["unreadable"]:
        raise MigrationError("CHARACTER_LIBRARY_INTEGRITY", f"head schema：{plan_heads}（支援 v{CHARACTER_SCHEMA_VERSION}）")
    problems: list[str] = []
    try:
        for rec in cs.list(include_archived=True):
            problems += cs.verify_history(rec.definition.character_id)
    except (CharacterStoreError, ValueError) as e:
        problems.append(str(e))
    if problems:
        raise MigrationError("CHARACTER_LIBRARY_INTEGRITY", "; ".join(problems))
    # Reference Library integrity（只看主 Library 已登記 asset）
    try:
        bad = [f"{e.rel_path}: {', '.join(e.problems)}" for e in ReferenceLibrary(ws).list(include_legacy=False) if e.problems]
    except ReferenceLibraryError as e:
        bad = [str(e)]
    if bad:
        raise MigrationError("REFERENCE_LIBRARY_INTEGRITY", "; ".join(bad))
    # Batch 4.1 reviewed plan（重新計算；不信任檔案中的舊報告）
    base = analyze(project_id, ws)
    dbytes = Path(decisions_path).read_bytes()
    doc, load_errors, dsha = md.load_decisions(Path(decisions_path))
    res = md.apply_decisions(base, doc, cs, load_errors=load_errors, decisions_file_sha256=dsha)
    rep, s = res["report"], res["report"]["summary"]
    dec = rep["decisions"]
    if dec["status"] != "applied" or dec["errors"]:
        code = "DECISIONS_STALE" if dec["status"] == "stale" else "DECISIONS_REJECTED"
        raise MigrationError(code, "; ".join(f"{e['code']} {e['legacy_id'] or ''} {e['detail']}".strip() for e in dec["errors"]))
    if not (s["migration_ready"] and s["blocking_conflicts"] == 0 and s["unresolved_entries"] == 0):
        raise MigrationError("NOT_MIGRATION_READY", "; ".join(s["not_ready_reasons"]))
    if not isinstance(doc, dict) or doc.get("migration_decisions_schema_version") != md.MIGRATION_DECISIONS_SCHEMA_VERSION:
        raise MigrationError("DECISIONS_REJECTED", "unsupported decisions schema")
    plan = rep["proposed_rewrite_plan"]
    for it in plan:
        if it["target_kind"] == "project_narrator_setting_placeholder":
            raise MigrationError("APPLY_UNSUPPORTED_IN_BATCH5", f"{it['legacy_id']}：Project 旁白設定 schema 尚未定義")
        if "scene_id" not in it and not it["field"].startswith("script."):
            raise MigrationError("APPLY_UNSUPPORTED_IN_BATCH5",
                                 f"{it['legacy_id']} {it['field']}：Project.characters 條目的處置（legacy_characters／production 相容）尚無規格")
    accepted = dec["accepted"]
    phash = md.plan_sha256(project_id, rep["report_input_hash"], base["report_sha256"], dsha, accepted, plan)
    token = phash[:12]
    if s["apply_confirmation_token"] != token:
        raise MigrationError("PLAN_HASH_MISMATCH", "internal plan hash mismatch")
    if not confirm or confirm.strip().lower() != token:
        raise MigrationError("CONFIRMATION_REQUIRED",
                             "請先以 --dry-run --decisions 審查報告，再用 --confirm <apply_confirmation_token> 執行")
    # 每個條目的處置
    entries = {e["legacy_id"]: e for e in rep["entries"]}
    creates, binds = [], []
    for lid in sorted({it["legacy_id"] for it in plan}):
        e = entries[lid]
        if e["planned_disposition"] == "new_library_character_placeholder":
            name = (e["decision"] or {}).get("display_name") or e["legacy_display_name"] or e["script_name"]
            if not name:
                raise MigrationError("MISSING_DISPLAY_NAME", lid)
            if e["source"] == "project.characters":
                raise MigrationError("APPLY_UNSUPPORTED_IN_BATCH5", f"{lid}：Project.characters 條目建立新角色尚無 legacy 處置規格")
            creates.append({"legacy_id": lid, "display_name": name})
        elif e["planned_disposition"] == "existing_library_character_pinned":
            d = e["decision"]
            binds.append({"legacy_id": lid, "character_id": d["library_character_id"], "character_revision": d["library_revision"],
                          "content_sha256": d["library_revision_content_sha256"]})
        else:
            raise MigrationError("APPLY_UNSUPPORTED_IN_BATCH5", f"{lid}: {e['planned_disposition']}")
    return {"project_id": project_id, "workspace": ws, "project_file": pfile, "project_bytes": project_bytes, "raw": raw,
            "base": base, "report": rep, "report_sha256": res["report_sha256"], "decisions_bytes": dbytes, "decisions_sha256": dsha,
            "plan": plan, "plan_sha256": phash, "token": token, "creates": creates, "binds": binds, "accepted": accepted}


# ---------------------------------------------------------------- backup
def create_backup(ctx: dict[str, Any], migration_id: str) -> Path:
    """原子建立 backup（`.partial` → rename）；不覆寫既有；只含 JSON（project.json、Scene manifest、決定檔、報告、計畫）。"""
    from see.storage.project_store import ProjectStore

    ws, pid = ctx["workspace"], ctx["project_id"]
    root = backups_dir(ws, pid)
    final = root / migration_id
    part = root / f"{migration_id}.partial"
    if final.exists() or part.exists():
        raise MigrationError("BACKUP_EXISTS", str(final))
    part.mkdir(parents=True)
    try:
        files: dict[str, str] = {}

        def put(rel: str, data: bytes) -> None:
            p = part / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "xb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            files[rel] = _bsha(data)

        put("project.json", ctx["project_bytes"])
        pdir = ProjectStore(ws).project_dir(pid)
        manifests = {}
        for m in sorted(pdir.glob("scenes/*/manifest.json")):
            b = m.read_bytes()
            rel = m.relative_to(pdir).as_posix()
            put(f"scene_manifests/{rel}", b)
            manifests[rel] = _bsha(b)
        put("decisions.json", ctx["decisions_bytes"])
        put("dry_run_with_decisions_report.json", _dump({"report_sha256": ctx["report_sha256"], "report": ctx["report"]}).encode())
        put("migration_plan.json", _dump({"plan_sha256": ctx["plan_sha256"], "plan": ctx["plan"]}).encode())
        manifest = {"backup_schema_version": BACKUP_SCHEMA_VERSION, "migration_id": migration_id, "project_id": pid,
                    "created_at": _now(), "files": files, "original_project_sha256": _bsha(ctx["project_bytes"]),
                    "original_scene_manifest_sha256": manifests, "report_input_hash": ctx["report"]["report_input_hash"],
                    "base_report_sha256": ctx["base"]["report_sha256"], "decisions_file_sha256": ctx["decisions_sha256"],
                    "plan_sha256": ctx["plan_sha256"],
                    "schema_versions": {"migration_report": ctx["report"]["migration_report_schema_version"],
                                        "migration_decisions": md.MIGRATION_DECISIONS_SCHEMA_VERSION,
                                        "migration_record": MIGRATION_RECORD_SCHEMA_VERSION},
                    "note": "不含任何圖片／私人素材；僅 JSON。不進 Git。"}
        put("backup_manifest.json", _dump(manifest).encode())
        os.rename(part, final)
    except Exception:
        shutil.rmtree(part, ignore_errors=True)  # 只刪本次自己建立、尚未成立的 .partial
        raise
    return final


def verify_backup(path: Path) -> dict[str, Any]:
    man = json.loads((path / "backup_manifest.json").read_text(encoding="utf-8"))
    for rel, sha in man["files"].items():
        p = path / rel
        if not p.is_file() or _bsha(p.read_bytes()) != sha:
            raise MigrationError("BACKUP_INTEGRITY", rel)
    return man


# ---------------------------------------------------------------- staging（新角色）
def _stage_characters(ctx: dict[str, Any], migration_id: str, staging: Path) -> list[dict[str, Any]]:
    from see.models.character_definition import CharacterDefinition
    from see.storage import character_store as csm

    real = csm.CharacterStore(ctx["workspace"])
    st = csm.CharacterStore(ctx["workspace"])  # 同 workspace（reference snapshot 讀真 Library）；寫入改到 staging
    st.root = staging / "character_library"
    out, taken = [], set()
    for c in ctx["creates"]:
        cid = None
        for _ in range(10):
            cand = csm.new_character_id()
            if cand in taken or real._path(cand).exists() or real.has_history(cand) or cand == PENDING_ID:
                continue
            cid = cand
            break
        if cid is None:
            raise MigrationError("ID_ALLOCATION_FAILED", "無法產生唯一的 Library character_id（collision）")
        taken.add(cid)
        rec = csm.CharacterRecord(definition=CharacterDefinition(character_id=cid, display_name=c["display_name"]))
        rev = st._append(rec, "create", None, migration_id=migration_id, project_id=ctx["project_id"], legacy_id=c["legacy_id"],
                         source="character_migration_batch5")
        st._save_head(rec)
        if st.verify_revision(cid, 1):
            raise MigrationError("STAGED_REVISION_INTEGRITY", cid)
        out.append({"legacy_id": c["legacy_id"], "character_id": cid, "character_revision": 1, "content_sha256": rev.content_sha256,
                    "display_name": c["display_name"]})
    return out


def _commit_characters(ctx: dict[str, Any], staging: Path, created: list[dict[str, Any]], moved: list[str]) -> None:
    from see.storage.character_store import HISTORY_DIR, CharacterStore

    real = CharacterStore(ctx["workspace"])
    (real.root / HISTORY_DIR).mkdir(parents=True, exist_ok=True)
    for c in created:
        cid = c["character_id"]
        src_h, dst_h = staging / "character_library" / HISTORY_DIR / cid, real.root / HISTORY_DIR / cid
        src_f, dst_f = staging / "character_library" / f"{cid}.json", real._path(cid)
        if dst_h.exists() or dst_f.exists():
            raise MigrationError("ID_ALLOCATION_FAILED", f"{cid} 已出現在 Library（collision）")
        os.rename(src_h, dst_h)
        moved.append(cid)
        os.rename(src_f, dst_f)


def _archive_created(ws: Path, ids: list[str], reason: str) -> dict[str, str]:
    """rollback 語意（D-066 §8.1）：本次新建角色 archive（不 hard delete；history 保留）。已被其他專案 cast 使用 → 保持 active。"""
    from see.storage.character_store import CharacterStore, CharacterStoreError
    from see.storage.project_store import ProjectStore

    cs, ps = CharacterStore(ws), ProjectStore(ws)
    used: set[str] = set()
    for pid in ps.list_projects():
        try:
            used |= {b.character_id for b in ps.load(pid).cast}
        except (ValueError, OSError):
            continue
    out: dict[str, str] = {}
    for cid in ids:
        if not cs._path(cid).exists() and not cs.has_history(cid):
            out[cid] = "not_in_library"
        elif cid in used:
            out[cid] = "kept_active_used_by_other_project"
        else:
            try:
                cs.archive(cid)
                out[cid] = f"archived_{reason}"
            except (CharacterStoreError, KeyError) as e:
                out[cid] = f"archive_failed: {e}"
    return out


# ---------------------------------------------------------------- post-verify
def post_verify(ctx: dict[str, Any], expected_bytes: bytes, created: list[dict[str, Any]], cast: list[dict[str, Any]],
                id_map: dict[str, str]) -> list[str]:
    from see.core.cast import resolve_project_cast
    from see.storage.character_store import CharacterStore
    from see.storage.project_store import ProjectStore

    ws, pid = ctx["workspace"], ctx["project_id"]
    errs: list[str] = []
    cur = ctx["project_file"].read_bytes()
    if cur != expected_bytes:
        errs.append("project.json 與 staged 內容不同")
    try:
        project = ProjectStore(ws).load(pid)
    except ValueError as e:
        return errs + [f"project 無法重新載入：{e}"]
    ids = [b.character_id for b in project.cast]
    if len(ids) != len(set(ids)) or len(ids) != len(cast):
        errs.append(f"cast ID 不唯一或數量不符：{ids}")
    cs = CharacterStore(ws)
    for c in created:
        errs += cs.verify_history(c["character_id"])
    rep = resolve_project_cast(project, cs)
    if rep.status == "error":
        errs += [f"cast {e.binding.character_id}@{e.binding.character_revision}: {e.error}" for e in rep.entries if e.integrity == "error"]
    for e in rep.entries:
        want = {b["character_id"]: b["content_sha256"] for b in cast}
        if e.content_sha256 != want.get(e.binding.character_id):
            errs.append(f"cast {e.binding.character_id} content_sha256 不符")
    raw = json.loads(cur.decode("utf-8"))
    for it in ctx["plan"]:
        try:
            c, k = _locate(raw, it)
        except MigrationError as e:
            errs.append(str(e))
            continue
        if c[k] != id_map[it["legacy_id"]]:
            errs.append(f"{it.get('scene_id', '')} {it['field']} 未改寫")
    if _mask(raw, ctx["plan"]) != _mask(ctx["raw"], ctx["plan"]):
        errs.append("計畫以外的 project 欄位被改動")
    pdir = ProjectStore(ws).project_dir(pid)
    man = verify_backup(backups_dir(ws, pid) / ctx["migration_id"])
    for rel, sha in man["original_scene_manifest_sha256"].items():
        p = pdir / rel
        if not p.is_file() or _bsha(p.read_bytes()) != sha:
            errs.append(f"scene manifest 被改動：{rel}")
    return errs


# ---------------------------------------------------------------- apply（transaction）
def apply(project_id: str, ws: Path, decisions_path: Path, confirm: str | None, *,
          _hooks: dict[str, Callable[..., Any]] | None = None) -> dict[str, Any]:
    """執行 migration（全有或全無）。成功 → record（status=committed）。失敗 → MigrationError（已恢復；record status=failed）。"""
    hooks = _hooks or {}
    ws = Path(ws)
    preflight(project_id, ws, decisions_path, confirm)  # 先唯讀檢查：不符 → 不建立任何檔案／目錄
    mdir = migrations_dir(ws, project_id)
    mdir.mkdir(parents=True, exist_ok=True)
    lock = mdir / ".lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as e:
        raise MigrationError("MIGRATION_LOCKED", f"{lock}（另一個 migration 正在執行，或上次異常中止；確認後手動移除）") from e
    os.close(fd)
    try:
        return _apply_locked(project_id, ws, decisions_path, confirm, hooks)
    finally:
        lock.unlink(missing_ok=True)


def _apply_locked(project_id, ws, decisions_path, confirm, hooks) -> dict[str, Any]:
    from see.models.project import Project

    ctx = preflight(project_id, ws, decisions_path, confirm)  # lock 內再確認一次（失敗 → 尚未寫任何資料）
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    mid = f"mig_{stamp}_{ctx['token'][:8]}"
    ctx["migration_id"] = mid
    rec_path = migrations_dir(ws, project_id) / f"{mid}.json"
    record: dict[str, Any] = {
        "migration_record_schema_version": MIGRATION_RECORD_SCHEMA_VERSION, "kind": "character_migration_record", "notice": NOTICE,
        "migration_id": mid, "project_id": project_id, "status": "preparing", "started_at": _now(),
        "plan_sha256": ctx["plan_sha256"], "apply_confirmation_token": ctx["token"],
        "report_input_hash": ctx["report"]["report_input_hash"], "base_report_sha256": ctx["base"]["report_sha256"],
        "decisions_file_sha256": ctx["decisions_sha256"], "decisions": ctx["accepted"],
        "original_project_sha256": _bsha(ctx["project_bytes"]), "planned_rewrite_count": len(ctx["plan"]),
        "backup_id": mid, "backup_path": f"backups/character_migrations/{project_id}/{mid}", "events": []}

    def log(status: str, **kw: Any) -> None:
        record.update(status=status, **kw)
        record["events"].append({"at": _now(), "status": status})
        _write_atomic(rec_path, _dump(record))

    staging = migrations_dir(ws, project_id) / f"{mid}.staging"
    moved: list[str] = []
    committed_project = False
    try:
        (hooks.get("backup") or create_backup)(ctx, mid)
    except MigrationError:
        raise
    except Exception as e:
        raise MigrationError("BACKUP_FAILED", str(e)) from e
    log("backed_up")
    try:
        created = _stage_characters(ctx, mid, staging)
        id_map = {c["legacy_id"]: c["character_id"] for c in created}
        id_map.update({b["legacy_id"]: b["character_id"] for b in ctx["binds"]})
        cast = [{"character_id": c["character_id"], "character_revision": c["character_revision"], "content_sha256": c["content_sha256"]}
                for c in created] + [{k: b[k] for k in ("character_id", "character_revision", "content_sha256")} for b in ctx["binds"]]
        cast_json = [{"character_id": b["character_id"], "character_revision": b["character_revision"], "role_label": "", "alias": "",
                      "follow": "pinned"} for b in sorted(cast, key=lambda x: x["character_id"])]
        staged, count = (hooks.get("stage_project") or stage_project)(ctx["raw"], ctx["plan"], id_map, cast_json)
        if count != len(ctx["plan"]) or count != ctx["report"]["summary"]["planned_rewrite_references"]:
            raise MigrationError("REWRITE_COUNT_MISMATCH", f"{count}")
        Project.model_validate(staged)  # staged 結果必須是合法 Project
        staged_text = json.dumps(staged, ensure_ascii=False, indent=2)
        staged_bytes = staged_text.encode("utf-8")
        # 寫入前最後確認：project.json 未被改動（planning 與 apply 之間）
        if ctx["project_file"].read_bytes() != ctx["project_bytes"]:
            raise MigrationError("PROJECT_CHANGED_DURING_APPLY", "")
        log(COMMITTING, created_characters=created, id_map=id_map, cast=cast, migrated_project_sha256=_bsha(staged_bytes))
        _commit_characters(ctx, staging, created, moved)
        if "commit_project" in hooks:
            hooks["commit_project"](ctx, staged_text)
        _write_atomic(ctx["project_file"], staged_bytes)
        committed_project = True
        errs = (hooks.get("post_verify") or post_verify)(ctx, staged_bytes, created, cast, id_map)
        if errs:
            raise MigrationError("POST_VERIFY_FAILED", "; ".join(errs))
    except Exception as e:
        err = e if isinstance(e, MigrationError) else MigrationError("APPLY_FAILED", repr(e))
        restored = False
        if committed_project or ctx["project_file"].read_bytes() != ctx["project_bytes"]:
            _write_atomic(ctx["project_file"], ctx["project_bytes"])
            restored = True
        arch = _archive_created(ws, moved, "by_auto_rollback") if moved else {}
        shutil.rmtree(staging, ignore_errors=True)  # staging 只含本次未提交的暫存檔
        ok = ctx["project_file"].read_bytes() == ctx["project_bytes"]
        log(FAILED, error={"code": err.code, "detail": err.detail}, project_restored_from_backup=restored,
            project_matches_original=ok, migration_created_characters=arch, finished_at=_now())
        raise err from e
    shutil.rmtree(staging, ignore_errors=True)
    log(COMMITTED, rewrite_count=count, finished_at=_now(),
        legacy_to_library=[{"legacy_id": k, "character_id": v,
                            "character_revision": next(c["character_revision"] for c in cast if c["character_id"] == v),
                            "decision": next((d["action"] for d in ctx["accepted"] if d["legacy_id"] == k), None)}
                           for k, v in sorted(id_map.items())])
    return record


# ---------------------------------------------------------------- rollback
def rollback(project_id: str, ws: Path, migration_id: str) -> dict[str, Any]:
    ws = Path(ws)
    if not re.fullmatch(r"mig_[0-9A-Za-z_]+", migration_id or ""):
        raise MigrationError("MIGRATION_NOT_FOUND", migration_id)
    rec_path = migrations_dir(ws, project_id) / f"{migration_id}.json"
    if not rec_path.is_file():
        raise MigrationError("MIGRATION_NOT_FOUND", migration_id)
    record = json.loads(rec_path.read_text(encoding="utf-8"))
    if record.get("project_id") != project_id:
        raise MigrationError("MIGRATION_PROJECT_MISMATCH", migration_id)
    if record.get("status") == ROLLED_BACK:
        raise MigrationError("ALREADY_ROLLED_BACK", migration_id)
    if record.get("status") not in (COMMITTED, COMMITTING):
        raise MigrationError("NOTHING_TO_ROLL_BACK", f"status={record.get('status')}")
    from see.storage.project_store import ProjectStore

    man = verify_backup(backups_dir(ws, project_id) / record["backup_id"])
    if man["project_id"] != project_id or man["migration_id"] != migration_id:
        raise MigrationError("BACKUP_INTEGRITY", "backup 不屬於此 migration")
    original = (backups_dir(ws, project_id) / record["backup_id"] / "project.json").read_bytes()
    pfile = ProjectStore(ws).project_file(project_id)
    cur = pfile.read_bytes() if pfile.is_file() else b""
    if _bsha(cur) not in (record.get("migrated_project_sha256"), record["original_project_sha256"]):
        raise MigrationError("PROJECT_MODIFIED_AFTER_MIGRATION",
                             "project.json 在 migration 後已被修改；rollback 會丟失這些修改 → 拒絕（請先人工處理）")
    if cur != original:
        _write_atomic(pfile, original)
    arch = _archive_created(ws, [c["character_id"] for c in record.get("created_characters", [])], "by_rollback")
    shutil.rmtree(migrations_dir(ws, project_id) / f"{migration_id}.staging", ignore_errors=True)
    if pfile.read_bytes() != original:
        raise MigrationError("ROLLBACK_VERIFY_FAILED", "project.json 未恢復")
    record.update(status=ROLLED_BACK, rolled_back_at=_now(), migration_created_characters=arch)
    record["events"].append({"at": _now(), "status": ROLLED_BACK})
    _write_atomic(rec_path, _dump(record))
    return record
