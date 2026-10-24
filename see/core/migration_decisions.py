"""Migration Human Decisions Layer（D-070 Batch 4.1）：以 versioned 人工決定檔重新計算 character-migrate dry-run 的 migration_ready。

**Batch 4.1 remains analysis-only. No project has been migrated.**
- 只讀：決定檔只被讀取；不寫 Project（含 cast／characters／Scene 引用）、Character Library／history、Reference Library。
- `create_new` 只產生 placeholder `pending_new_character_id`；**不產生任何正式 Library Character ID**（D-067：正式 ID 只在 Batch 5 apply 時由系統產生）。
- `migration_ready=true` 只代表「可以進入經審查的 migration planning」，**不代表已遷移，也不代表 Batch 5 已核准**。
- Fail closed：決定檔任何錯誤（格式、未知欄位、ID、action 不適用、Library revision 問題）→ 整份不採用（all-or-nothing），migration_ready=false。
- Stale：決定檔的 `source_report_input_hash`／`source_report_sha256` 必須與本次重新計算的基礎 dry-run 完全一致；不一致 → `stale`，不採用任何決定。
- 決定只能解決「這個條目怎麼處置」的衝突；欄位層級衝突（性別／年齡／自由文字外觀／reference／未知欄位）在會帶入資料的 action
  （create_new）下**不會被解決**（v1 決定檔沒有欄位決定；見 docs/CHARACTER_LIBRARY_PROJECT_BINDING.md §8.5）。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from see.core.character_migration import PENDING_ID, _sha

MIGRATION_DECISIONS_SCHEMA_VERSION = 1
DECISIONS_KIND = "character_migration_decisions"
NOTICE = "Batch 4.1 remains analysis-only. No project has been migrated."
READINESS_SCOPE = "ready_for_reviewed_migration_planning_only（不代表已遷移；不代表 Batch 5 已核准）"
NARRATOR_PLACEHOLDER = "pending_project_narrator_setting"

CREATE_NEW = "create_new"
BIND_EXISTING = "bind_existing"
KEEP_LEGACY = "keep_legacy"
NARRATOR = "narrator_setting"
IGNORE_UNUSED = "ignore_unused"
ACTIONS = (CREATE_NEW, BIND_EXISTING, KEEP_LEGACY, NARRATOR, IGNORE_UNUSED)

TOP_KEYS = {"migration_decisions_schema_version", "kind", "project_id", "source_report_input_hash", "source_report_sha256",
            "decisions", "note"}
TOP_REQUIRED = ("migration_decisions_schema_version", "kind", "project_id", "source_report_input_hash", "source_report_sha256",
                "decisions")
DECISION_KEYS = {  # action → 允許的欄位（legacy_id／action／note 永遠允許）
    CREATE_NEW: {"display_name"},
    BIND_EXISTING: {"library_character_id", "library_revision"},
    KEEP_LEGACY: set(),
    NARRATOR: set(),
    IGNORE_UNUSED: set(),
}
BASE_DECISION_KEYS = {"legacy_id", "action", "note"}

# 固定錯誤碼（決定檔驗證；任何一個 → 整份不採用）
ERRORS: dict[str, str] = {
    "DECISIONS_INVALID_JSON": "決定檔不是合法 JSON",
    "DECISIONS_SCHEMA_INVALID": "決定檔結構不合法（缺必要欄位或型別錯誤）",
    "DECISIONS_SCHEMA_UNSUPPORTED": "決定檔 schema 版本不支援（比程式新或無效）",
    "DECISIONS_KIND_INVALID": "kind 必須是 character_migration_decisions",
    "DECISIONS_UNKNOWN_FIELD": "決定檔含不認得的欄位",
    "DECISIONS_PROJECT_MISMATCH": "決定檔的 project_id 與本次分析的專案不同",
    "DECISIONS_STALE": "決定檔對應的 dry-run 報告已過期（專案／Library／reference 或分析規則已改變）；請重新跑 dry-run 並重新決定",
    "DECISION_INVALID": "單一決定格式不合法",
    "DECISION_UNKNOWN_LEGACY_ID": "legacy_id 不在本次 dry-run 報告中",
    "DECISION_DUPLICATE": "同一個 legacy_id 有多筆決定",
    "DECISION_INVALID_ACTION": "action 不在允許清單內",
    "DECISION_FIELD_REQUIRED": "此 action 缺少必要欄位",
    "DECISION_FIELD_NOT_ALLOWED": "此 action 不允許這個欄位",
    "DECISION_FIELD_INVALID": "欄位值不合法",
    "DECISION_ACTION_NOT_APPLICABLE": "此 action 不適用於這個條目",
    "DECISION_LIBRARY_CHARACTER_NOT_FOUND": "指定的 Library 角色不存在",
    "DECISION_LIBRARY_CHARACTER_ARCHIVED": "指定的 Library 角色已封存；新綁定被拒絕（需先 restore）",
    "DECISION_LIBRARY_REVISION_NOT_FOUND": "指定的 Library revision 不存在（不 fallback 到 latest）",
    "DECISION_LIBRARY_REVISION_INTEGRITY": "指定的 Library revision 完整性檢查失敗（hash 不符或檔案損壞）",
}

# 各 action 可以解決的 blocking conflict（固定規則；不在清單內的 blocking conflict 仍然 blocking）
_DISPOSITION = {"SCRIPT_ONLY_CHARACTER", "UNUSED_CHARACTER", "ID_NAMESPACE_CONFLICT", "LIBRARY_MATCH_CANDIDATE",
                "MULTIPLE_LIBRARY_MATCHES", "NAME_CONFLICT", "MISSING_DISPLAY_NAME", "SCENE_REFERENCE_INCONSISTENT"}
_FIELD_LEVEL = {"GENDER_MAPPING_AMBIGUOUS", "AGE_MAPPING_AMBIGUOUS", "FREE_TEXT_APPEARANCE", "REFERENCE_MISSING",
                "REFERENCE_UNREGISTERED", "REFERENCE_HASH_CONFLICT", "UNKNOWN_FIELD"}
RESOLVES: dict[str, set[str]] = {
    # 新角色會帶入 legacy 資料 → 欄位層級衝突與 VOICE_ROLE_AMBIGUOUS 不解決
    CREATE_NEW: set(_DISPOSITION),
    # 綁既有 Library 角色：Library revision 為權威，legacy 資料不合併（保留在 legacy）→ 欄位層級衝突不再適用
    BIND_EXISTING: _DISPOSITION | _FIELD_LEVEL,
    # 不建立 Library 角色、資料原樣留在 legacy → 處置與欄位衝突都不再適用
    KEEP_LEGACY: _DISPOSITION | _FIELD_LEVEL,
    IGNORE_UNUSED: _DISPOSITION | _FIELD_LEVEL,
    NARRATOR: _DISPOSITION | _FIELD_LEVEL | {"VOICE_ROLE_AMBIGUOUS"},
}
NEVER_RESOLVED = {"PROJECT_ALREADY_HAS_CAST"}

_SCENE_REF_KINDS = ("scene_character_ids", "scene_overrides", "gaze_targets", "dialogue", "script_beats")
_VISUAL_KINDS = ("scene_character_ids", "scene_overrides", "gaze_targets", "dialogue")


def _err(code: str, legacy_id: str | None = None, detail: str = "") -> dict[str, Any]:
    return {"code": code, "legacy_id": legacy_id, "message": ERRORS[code], "detail": detail}


def applicable_actions(entry: dict[str, Any]) -> list[str]:
    """這個條目可以選的 action（確定性；依 usage 與來源）。"""
    u = entry["usage_counts"]
    refs = sum(u[k] for k in _SCENE_REF_KINDS) + u["narration"]
    visual = sum(u[k] for k in _VISUAL_KINDS)
    out = [CREATE_NEW, BIND_EXISTING]
    if entry["source"] == "project.characters" and refs == 0:
        out.append(KEEP_LEGACY)  # 資料留在 legacy；不能有任何引用（否則遷移後引用懸空）
    if u["narration"] > 0 and visual == 0:
        out.append(NARRATOR)
    if refs == 0:
        out.append(IGNORE_UNUSED)
    return out


def _entry_name(entry: dict[str, Any]) -> str:
    return entry["legacy_display_name"] or entry["script_name"] or ""


def load_decisions(path: Path) -> tuple[Any, list[dict[str, Any]], str | None]:
    """讀決定檔（只讀）。回傳 (doc, errors, decisions_file_sha256)。"""
    data = Path(path).read_bytes()
    from hashlib import sha256

    digest = sha256(data).hexdigest()
    try:
        return json.loads(data.decode("utf-8")), [], digest
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, [_err("DECISIONS_INVALID_JSON", None, str(e))], digest


def validate(doc: Any, base: dict[str, Any], store: Any) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """確定性驗證。回傳 (legacy_id → 決定, errors)。errors 非空 → 呼叫端不得採用任何決定。"""
    report = base["report"]
    errors: list[dict[str, Any]] = []
    if not isinstance(doc, dict):
        return {}, [_err("DECISIONS_SCHEMA_INVALID", None, "最上層必須是 JSON object")]
    for k in TOP_REQUIRED:
        if k not in doc:
            errors.append(_err("DECISIONS_SCHEMA_INVALID", None, f"缺少 {k}"))
    for k in sorted(set(doc) - TOP_KEYS):
        errors.append(_err("DECISIONS_UNKNOWN_FIELD", None, k))
    ver = doc.get("migration_decisions_schema_version")
    if "migration_decisions_schema_version" in doc and (type(ver) is not int or ver != MIGRATION_DECISIONS_SCHEMA_VERSION):
        errors.append(_err("DECISIONS_SCHEMA_UNSUPPORTED", None, f"{ver!r}（支援 {MIGRATION_DECISIONS_SCHEMA_VERSION}）"))
    if "kind" in doc and doc["kind"] != DECISIONS_KIND:
        errors.append(_err("DECISIONS_KIND_INVALID", None, repr(doc["kind"])))
    if "project_id" in doc and doc["project_id"] != report["project_id"]:
        errors.append(_err("DECISIONS_PROJECT_MISMATCH", None, f"{doc['project_id']!r} ≠ {report['project_id']!r}"))
    for k, cur in (("source_report_input_hash", report["report_input_hash"]), ("source_report_sha256", base["report_sha256"])):
        if k not in doc:
            continue
        if not isinstance(doc[k], str):
            errors.append(_err("DECISIONS_SCHEMA_INVALID", None, f"{k} 必須是字串"))
        elif doc[k] != cur:
            errors.append(_err("DECISIONS_STALE", None, f"{k}：決定檔 {doc[k][:12]}… ≠ 目前 {cur[:12]}…"))
    if "note" in doc and not isinstance(doc["note"], str):
        errors.append(_err("DECISIONS_SCHEMA_INVALID", None, "note 必須是字串"))
    decs = doc.get("decisions")
    if "decisions" in doc and not isinstance(decs, list):
        errors.append(_err("DECISIONS_SCHEMA_INVALID", None, "decisions 必須是陣列"))
        decs = []
    entries = {e["legacy_id"]: e for e in report["entries"]}
    accepted: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for i, d in enumerate(decs or []):
        if not isinstance(d, dict) or not isinstance(d.get("legacy_id"), str) or not d["legacy_id"]:
            errors.append(_err("DECISION_INVALID", None, f"decisions[{i}] 必須是含 legacy_id 字串的 object"))
            continue
        lid = d["legacy_id"]
        if lid in seen:
            errors.append(_err("DECISION_DUPLICATE", lid, f"decisions[{i}]"))
            continue
        seen.add(lid)
        e = entries.get(lid)
        if e is None:
            errors.append(_err("DECISION_UNKNOWN_LEGACY_ID", lid))
            continue
        action = d.get("action")
        if action not in ACTIONS:
            errors.append(_err("DECISION_INVALID_ACTION", lid, f"{action!r}；允許：{', '.join(ACTIONS)}"))
            continue
        for k in sorted(set(d) - BASE_DECISION_KEYS - DECISION_KEYS[action]):
            errors.append(_err("DECISION_FIELD_NOT_ALLOWED", lid, f"{action} 不接受 {k}"))
        if "note" in d and not isinstance(d["note"], str):
            errors.append(_err("DECISION_FIELD_INVALID", lid, "note 必須是字串"))
        if action not in applicable_actions(e):
            errors.append(_err("DECISION_ACTION_NOT_APPLICABLE", lid, f"{action}；此條目可用：{', '.join(applicable_actions(e))}"))
            continue
        before = len(errors)
        out: dict[str, Any] = {"legacy_id": lid, "action": action}
        if action == CREATE_NEW:
            codes = {c["code"] for c in e["conflicts"]}
            need_name = not _entry_name(e) or bool(codes & {"NAME_CONFLICT", "MISSING_DISPLAY_NAME"})
            if "display_name" in d:
                dn = d["display_name"]
                if not isinstance(dn, str) or not dn.strip() or len(dn.strip()) > 64:
                    errors.append(_err("DECISION_FIELD_INVALID", lid, "display_name 必須是 1～64 字的非空字串"))
                else:
                    out["display_name"] = dn.strip()
            elif need_name:
                errors.append(_err("DECISION_FIELD_REQUIRED", lid, "沒有名稱或名稱有衝突：create_new 必須明確給 display_name"))
            out.setdefault("display_name", _entry_name(e))
            out["proposed_character_id"] = PENDING_ID
        elif action == BIND_EXISTING:
            cid, rev = d.get("library_character_id"), d.get("library_revision")
            if "library_character_id" not in d or "library_revision" not in d:
                errors.append(_err("DECISION_FIELD_REQUIRED", lid, "bind_existing 需要 library_character_id 與 library_revision（pinned）"))
            elif not isinstance(cid, str) or not cid or type(rev) is not int or rev < 1:
                errors.append(_err("DECISION_FIELD_INVALID", lid, "library_character_id 必須是字串、library_revision 必須是 ≥1 的整數"))
            else:
                errors.extend(_check_library(store, lid, cid, rev, out))
        if len(errors) == before:
            if "note" in d:
                out["note"] = d["note"]
            accepted[lid] = out
    errors.sort(key=lambda x: (x["code"], x["legacy_id"] or "", x["detail"]))
    return accepted, errors


def _check_library(store: Any, lid: str, cid: str, rev: int, out: dict[str, Any]) -> list[dict[str, Any]]:
    from see.storage.character_store import CharacterRevisionError, CharacterStoreError

    try:
        head = store.get(cid)
    except CharacterRevisionError as e:
        return [_err("DECISION_LIBRARY_REVISION_INTEGRITY", lid, f"目前狀態無法驗證：{e}")]
    except (KeyError, CharacterStoreError):
        return [_err("DECISION_LIBRARY_CHARACTER_NOT_FOUND", lid, cid)]
    if head.archived:
        return [_err("DECISION_LIBRARY_CHARACTER_ARCHIVED", lid, cid)]
    if rev not in store.list_revisions(cid):
        return [_err("DECISION_LIBRARY_REVISION_NOT_FOUND", lid, f"{cid}@{rev}")]
    try:
        r = store.read_revision(cid, rev)
    except CharacterRevisionError as e:
        return [_err("DECISION_LIBRARY_REVISION_INTEGRITY", lid, str(e))]
    if r.archived:
        return [_err("DECISION_LIBRARY_CHARACTER_ARCHIVED", lid, f"{cid}@{rev} 為封存狀態")]
    out.update(library_character_id=cid, library_revision=rev, library_revision_content_sha256=r.content_sha256,
               library_display_name=r.definition.display_name)
    return []


def plan_sha256(project_id: str, report_input_hash: str, base_report_sha256: str, decisions_file_sha256: str | None,
                accepted: list[dict[str, Any]], plan: list[dict[str, Any]]) -> str:
    """reviewed migration plan 的確定性指紋（D-071）：同一份輸入＋同一份決定檔＋同一份改寫計畫 → 同一 hash（same migration intent）。"""
    return _sha({"project_id": project_id, "report_input_hash": report_input_hash, "base_report_sha256": base_report_sha256,
                 "decisions_file_sha256": decisions_file_sha256, "accepted": accepted, "plan": plan})


# ---------------------------------------------------------------- 重新計算（只讀，回傳新報告）
def _plan_target(entry: dict[str, Any], decision: dict[str, Any] | None) -> tuple[str | None, Any]:
    """回傳 (target_kind, target)。None＝此條目沒有可執行的改寫目標。"""
    action = decision["action"] if decision else None
    if action == CREATE_NEW or (action is None and entry["proposed_action"] == "create_new_library_character"):
        return "new_library_character_placeholder", PENDING_ID
    if action == BIND_EXISTING:
        return "existing_library_character_pinned", {"character_id": decision["library_character_id"],
                                                     "character_revision": decision["library_revision"]}
    if action == NARRATOR or (action is None and entry["proposed_action"] == "propose_project_narrator_setting"):
        return "project_narrator_setting_placeholder", NARRATOR_PLACEHOLDER
    return None, None


def apply_decisions(base: dict[str, Any], doc: Any, store: Any, *, load_errors: list[dict[str, Any]] | None = None,
                    decisions_file_sha256: str | None = None) -> dict[str, Any]:
    """以人工決定重新計算 dry-run（不寫任何檔）。回傳 {"report": …, "report_sha256": …}。base＝analyze() 的結果（不被修改）。"""
    report = copy.deepcopy(base["report"])
    if load_errors:
        accepted, errors = {}, list(load_errors)
    else:
        accepted, errors = validate(doc, base, store)
    status = "applied" if not errors else ("stale" if any(e["code"] == "DECISIONS_STALE" for e in errors) else "rejected")
    use = accepted if status == "applied" else {}

    plan: list[dict[str, Any]] = []
    unresolved_ids: list[str] = []
    for e in report["entries"]:
        d = use.get(e["legacy_id"])
        blocking = sorted({c["code"] for c in e["conflicts"] if c["severity"] == "blocking"})
        resolved = sorted(set(blocking) & RESOLVES[d["action"]] - NEVER_RESOLVED) if d else []
        remaining = sorted(set(blocking) - set(resolved))
        needs = bool(remaining) or (e["requires_human_decision"] and d is None)
        e["applicable_actions"] = applicable_actions(e)
        e["decision"] = d
        e["resolved_conflicts"] = resolved
        e["remaining_blocking_conflicts"] = remaining
        e["decision_outcome"] = ("NO_DECISION_NEEDED" if not needs and d is None else
                                 "RESOLVED" if not needs else "UNRESOLVED")
        if needs:
            unresolved_ids.append(e["legacy_id"])
        kind, target = _plan_target(e, d) if not needs else (None, None)
        if d and d["action"] in (KEEP_LEGACY, IGNORE_UNUSED):
            e["planned_disposition"] = "keep_in_legacy_characters" if e["source"] == "project.characters" else "no_library_character"
        elif kind is None:
            e["planned_disposition"] = "unresolved" if needs else "keep_in_legacy_characters"
        else:
            e["planned_disposition"] = kind
        if kind is not None:
            for w in e["rewrites"]:
                plan.append({"legacy_id": e["legacy_id"], **w, "target_kind": kind, "target": target})

    plan.sort(key=lambda w: (w["legacy_id"], w.get("scene_id", ""), w["field"]))
    base_summary = report["summary"]
    not_ready: list[str] = []
    if status == "stale":
        not_ready.append("決定檔已過期（stale）：未採用任何決定")
    elif status == "rejected":
        not_ready.append(f"決定檔驗證失敗（{len(errors)} 個錯誤）：未採用任何決定")
    if unresolved_ids:
        not_ready.append(f"{len(unresolved_ids)} 個角色仍有未解決的 blocking conflict 或缺人工決定：{', '.join(unresolved_ids)}")
    if report["character_binding_state"] != "v0_legacy":
        not_ready.append("專案已有 Project.cast")
    if not report["entries"]:
        not_ready.append("沒有任何角色資料可遷移")
    remaining_blocking = sum(len(e["remaining_blocking_conflicts"]) for e in report["entries"])
    report.update(
        kind="character_migration_dry_run_with_decisions",
        notice=NOTICE,
        base_report_sha256=base["report_sha256"],
        base_summary=base_summary,
        decisions={
            "migration_decisions_schema_version": MIGRATION_DECISIONS_SCHEMA_VERSION,
            "status": status,
            "decisions_file_sha256": decisions_file_sha256,
            "source_report_input_hash": doc.get("source_report_input_hash") if isinstance(doc, dict) else None,
            "source_report_sha256": doc.get("source_report_sha256") if isinstance(doc, dict) else None,
            "accepted": [use[k] for k in sorted(use)],
            "errors": errors,
            "error_codes": ERRORS,
        },
        proposed_rewrite_plan=plan,
        summary={
            **{k: base_summary[k] for k in ("total_legacy_characters", "total_entries", "script_or_scene_only", "auto_mappable",
                                            "human_required", "legacy_only", "narrator_settings", "empty_unused",
                                            "affected_scenes", "affected_scene_count", "total_rewrite_references")},
            "decisions_status": status,
            "decisions_applied": len(use),
            "resolved_entries": sum(1 for e in report["entries"] if e["decision_outcome"] == "RESOLVED"),
            "unresolved_entries": len(unresolved_ids),
            "blocking_conflicts": remaining_blocking,
            "planned_rewrite_references": len(plan),
            "new_character_placeholders": sum(1 for e in report["entries"]
                                              if e["planned_disposition"] == "new_library_character_placeholder"),
            "migration_ready": not not_ready,
            "migration_ready_scope": READINESS_SCOPE,
            # D-071 Batch 5：`--apply --confirm <token>` 用的確定性短 token（＝plan_sha256 前 12 碼；只有 ready 時提供）
            "apply_confirmation_token": plan_sha256(report["project_id"], report["report_input_hash"], base["report_sha256"],
                                                    decisions_file_sha256, [use[k] for k in sorted(use)], plan)[:12]
            if not not_ready else None,
            "not_ready_reasons": not_ready,
        },
    )
    report["rules"] = {**report["rules"],
                       "decisions": "決定檔任何錯誤或過期 → 整份不採用（fail closed）；只解決處置類衝突，create_new 不解決欄位層級衝突",
                       "create_new_id": f"只用 placeholder {PENDING_ID}；不產生正式 Library Character ID",
                       "migration_ready_scope": READINESS_SCOPE}
    return {"report": report, "report_sha256": _sha(report)}


def decisions_template(base: dict[str, Any]) -> dict[str, Any]:
    """產生決定檔範本（只輸出；不寫 workspace）。每個需要人工決定的條目一筆，action=null 需使用者填寫（未填 → 驗證失敗）。"""
    r = base["report"]
    decs = [{"legacy_id": e["legacy_id"], "action": None,
             "note": f"「{_entry_name(e) or '（無名稱）'}」可用 action：{'、'.join(applicable_actions(e))}"}
            for e in r["entries"] if e["requires_human_decision"]]
    return {"migration_decisions_schema_version": MIGRATION_DECISIONS_SCHEMA_VERSION, "kind": DECISIONS_KIND,
            "project_id": r["project_id"], "source_report_input_hash": r["report_input_hash"],
            "source_report_sha256": base["report_sha256"], "note": NOTICE, "decisions": decs}


def human_summary(result: dict[str, Any]) -> str:
    r = result["report"]
    s = r["summary"]
    dz = {"applied": "已採用", "stale": "已過期（未採用）", "rejected": "驗證失敗（未採用）"}
    lines = [f"角色遷移 dry-run＋人工決定（只分析，未遷移任何資料）— 專案 {r['project_id']}",
             f"決定檔：{dz[s['decisions_status']]}；採用 {s['decisions_applied']} 筆",
             f"已解決 {s['resolved_entries']}｜未解決 {s['unresolved_entries']}｜剩餘 blocking 衝突 {s['blocking_conflicts']}｜"
             f"新角色 placeholder {s['new_character_placeholders']}｜計畫改寫引用 {s['planned_rewrite_references']} 處",
             f"可以進入 migration planning：{'是' if s['migration_ready'] else '否'}"
             + (f"（{'；'.join(s['not_ready_reasons'])}）" if s["not_ready_reasons"] else ""),
             "注意：即使為「是」，也只代表可進入經審查的 migration planning；本指令未遷移任何專案。", "---"]
    if s.get("apply_confirmation_token"):
        lines.insert(-1, f"apply_confirmation_token：{s['apply_confirmation_token']}（確認報告後，--apply 需 --confirm 這 12 碼）")
    for err in r["decisions"]["errors"]:
        lines.append(f"  [error] {err['code']}：{err['message']}" + (f"（{err['legacy_id']}）" if err["legacy_id"] else "")
                     + (f"：{err['detail']}" if err["detail"] else ""))
    for e in r["entries"]:
        d = e["decision"]
        lines.append(f"• {e['legacy_id']}「{_entry_name(e) or '（無名稱）'}」→ {e['decision_outcome']}；"
                     f"決定：{d['action'] if d else '（無）'}；處置：{e['planned_disposition']}")
        for c in e["remaining_blocking_conflicts"]:
            lines.append(f"    [blocking] {c}")
    lines.append(f"report_input_hash {r['report_input_hash']}")
    lines.append(f"base_report_sha256 {r['base_report_sha256']}")
    lines.append(f"report_sha256     {result['report_sha256']}")
    lines.append(NOTICE)
    return "\n".join(lines)
