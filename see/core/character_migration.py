"""Character migration dry-run（D-069 Batch 4）：分析舊 `Project.characters` 如何對應到 Character Library／Project.cast。

**Batch 4 only analyzes. No project has been migrated.**
- 只讀：不寫 Project、Character Library（含 history）、Scene、`.ref.json`；不登記／複製圖片；不 backup、不 rollback。
- 新角色 ID 一律以 `pending_new_character_id` 表示（DG-29：正式 ID 由系統在 Batch 5 apply 時產生；dry-run 不產生任何 ID）。
- 不因名字、性別或外觀文字相同就認定同一角色；既有 Library 對應只接受「唯一的 reference sha256」證據，且仍需人工確認。
- 報告確定性：所有清單排序、無時間戳；`report_sha256` 涵蓋整份語意內容；`report_input_hash` 涵蓋分析讀到的所有輸入。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from see.models.character_definition import ID_PATTERN, CharacterDefinition
from see.models.project import CharacterAppearance, CharacterTraits, CharacterVoice

MIGRATION_REPORT_SCHEMA_VERSION = 1
PENDING_ID = "pending_new_character_id"

# 分類
AUTO_MAPPABLE = "AUTO_MAPPABLE"
HUMAN_REQUIRED = "HUMAN_REQUIRED"
LEGACY_ONLY = "LEGACY_ONLY"
NARRATOR_SETTING = "NARRATOR_SETTING"
EMPTY_UNUSED = "EMPTY_UNUSED"
CLASSIFICATIONS = (AUTO_MAPPABLE, HUMAN_REQUIRED, LEGACY_ONLY, NARRATOR_SETTING, EMPTY_UNUSED)

# 固定 conflict code → (嚴重度, 中文說明)。blocking＝需人工決定才可能 migration_ready；info＝僅提示
CONFLICTS: dict[str, tuple[str, str]] = {
    "ID_NAMESPACE_CONFLICT": ("blocking", "舊專案內 ID 與既有 Library character_id 字串相同（不同命名空間，不得視為同一角色）"),
    "ID_FORMAT_LEGACY": ("info", "舊 ID 不符 Library ID 格式；migration 時一律改用系統產生的新 ID"),
    "NAME_CONFLICT": ("blocking", "名稱不一致（角色設定 vs 劇本）或與其他角色／既有 Library 角色同名；同名不代表同一角色"),
    "MISSING_DISPLAY_NAME": ("blocking", "沒有任何可用的顯示名稱"),
    "GENDER_MAPPING_AMBIGUOUS": ("blocking", "性別呈現是自由文字，不自動轉成 enum（不推論）"),
    "AGE_MAPPING_AMBIGUOUS": ("blocking", "整數年齡不自動轉成 age_impression 措辭"),
    "FREE_TEXT_APPEARANCE": ("blocking", "description_en／features_en 是自由文字，不自動拆欄位"),
    "LEGACY_ONLY_FIELDS": ("info", "seed／adapter（模型設定）或 body_type（無對應欄位）只保留在 legacy"),
    "REFERENCE_MISSING": ("blocking", "legacy reference 路徑找不到檔案"),
    "REFERENCE_UNREGISTERED": ("blocking", "reference 檔案存在但不在 Reference Library（需使用者登記；dry-run 不登記）"),
    "REFERENCE_HASH_CONFLICT": ("blocking", "相同 sha256 有多筆 Library asset，或 asset metadata 不一致，或已綁定其他角色"),
    "MULTIPLE_LIBRARY_MATCHES": ("blocking", "reference sha256 對應到多個既有 Library 角色"),
    "LIBRARY_MATCH_CANDIDATE": ("blocking", "reference sha256 唯一對應到既有 Library 角色：可能是同一角色，需人工確認（不自動合併）"),
    "VOICE_ROLE_AMBIGUOUS": ("blocking", "同時作為旁白與畫面角色，或旁白條目帶有外觀；角色／旁白身分不明"),
    "VOICE_DEFAULT_UNSPECIFIED": ("info", "voice_id 為 default：不建立 voice profile（不補值）"),
    "VOICE_CONFIRMATION_REBIND": ("info", "舊 voice 確認需在 migration 後綁到新 revision 重新確認"),
    "NARRATOR_NOT_CHARACTER": ("info", "僅作旁白聲音使用：應成為 Project 旁白設定，不建立 CharacterDefinition"),
    "EMPTY_CHARACTER": ("info", "只有 ID、沒有有效資料"),
    "UNUSED_CHARACTER": ("blocking", "有設定資料但從未被任何 Scene／對白／劇本引用；是否搬移需人工決定"),
    "SCRIPT_ONLY_CHARACTER": ("blocking", "只存在於劇本／Scene 引用、沒有角色設定；是否建立 Library 角色需人工決定"),
    "UNKNOWN_FIELD": ("blocking", "project.json 角色資料含程式不認得的欄位"),
    "SCENE_REFERENCE_INCONSISTENT": ("blocking", "Scene／對白引用了不存在於角色設定與劇本的 ID"),
    "PROJECT_ALREADY_HAS_CAST": ("blocking", "專案已有 Project.cast；不可重複遷移"),
}


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha(obj: Any) -> str:
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def _bytes_sha(p: Path) -> str:
    from see.core.hashing import file_sha256

    return file_sha256(p)


def _conflict(code: str, detail: str = "") -> dict[str, str]:
    sev, msg = CONFLICTS[code]
    return {"code": code, "severity": sev, "message": msg, "detail": detail}


# ---------------------------------------------------------------- 引用盤點
def _usage(project: Any) -> dict[str, dict[str, list[Any]]]:
    """每個 ID 在專案內被引用的位置（只讀）。"""
    u: dict[str, dict[str, list[Any]]] = {}

    def add(cid: str, kind: str, where: Any) -> None:
        u.setdefault(cid, {}).setdefault(kind, []).append(where)

    for s in project.scenes:
        for i, cid in enumerate(s.character_ids):
            add(cid, "scene_character_ids", {"scene_id": s.scene_id, "field": f"character_ids[{i}]"})
        for i, sc in enumerate(s.characters):
            add(sc.character_id, "scene_overrides", {"scene_id": s.scene_id, "field": f"characters[{i}].character_id"})
            if sc.gaze is not None and sc.gaze.target_character_id:
                add(sc.gaze.target_character_id, "gaze_targets", {"scene_id": s.scene_id, "field": f"characters[{i}].gaze.target_character_id"})
        for i, d in enumerate(s.dialogue):
            add(d.character_id, "dialogue", {"scene_id": s.scene_id, "field": f"dialogue[{i}].character_id"})
        if s.narrator_id:
            add(s.narrator_id, "narration", {"scene_id": s.scene_id, "field": "narrator_id"})
            if s.voice not in ("", "default"):
                add(s.narrator_id, "voice_overrides", {"scene_id": s.scene_id, "field": "voice", "value": s.voice})
    if project.script is not None:
        for i, c in enumerate(project.script.characters):
            add(c.character_id, "script_characters", {"field": f"script.characters[{i}].character_id"})
        for b in project.script.beats:
            for j, cid in enumerate(b.character_ids):
                add(cid, "script_beats", {"field": f"script.beats[{b.index}].character_ids[{j}]"})
    return u


ON_SCREEN = ("scene_character_ids", "scene_overrides", "gaze_targets", "dialogue", "script_characters", "script_beats")


# ---------------------------------------------------------------- Reference Library 索引（只讀）
def _ref_index(workspace: Path) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    from see.core.reference_library import ReferenceLibrary, ReferenceLibraryError

    try:
        entries = ReferenceLibrary(workspace).list(include_legacy=False)
    except ReferenceLibraryError:
        entries = []
    by_sha: dict[str, list[dict[str, Any]]] = {}
    meta: list[dict[str, Any]] = []
    for e in entries:
        if e.asset is None:
            continue
        d = {"asset_id": e.asset.asset_id, "rel_path": e.rel_path, "sha256": e.asset.sha256, "character_id": e.asset.character_id,
             "role": e.asset.role.value, "problems": list(e.problems)}
        by_sha.setdefault(e.asset.sha256, []).append(d)
        meta.append(d)
    return by_sha, sorted(meta, key=lambda x: x["rel_path"])


def _resolve_ref_path(raw: str, workspace: Path) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (workspace.parent / p)  # 相對路徑以 workspace 的上層（repo 根）為基準（文件化規則）


# ---------------------------------------------------------------- 單一條目分析
_AUTO_APPEARANCE = (("outfit_en", "outfit"),)
_AUTO_TRAITS = (("hair_style", "hair_style"), ("hair_color", "hair_color"), ("facial_features", "facial_features"),
                ("distinctive_marks", "distinctive_marks"), ("age_range", "age_impression"), ("appearance_region", "appearance_region"))


def _nonempty(v: Any) -> bool:
    return v not in (None, "", [], {})


def _analyze_entry(cid: str, raw: dict[str, Any] | None, cv: CharacterVoice | None, script_name: str | None,
                   usage: dict[str, list[Any]], ctx: dict[str, Any]) -> dict[str, Any]:
    conflicts: list[dict[str, str]] = []
    mappings: list[dict[str, Any]] = []
    legacy_only: list[str] = []
    references: list[dict[str, Any]] = []
    proposed_refs: list[str] = []
    library_candidates: set[str] = set()

    # ---- unknown fields（讀 raw JSON；pydantic 會默默略過未知欄位）
    if raw is not None:
        unknown = sorted(set(raw) - set(CharacterVoice.model_fields))
        app_raw = raw.get("appearance") or {}
        unknown += [f"appearance.{k}" for k in sorted(set(app_raw) - set(CharacterAppearance.model_fields))]
        tr_raw = app_raw.get("traits") or {}
        unknown += [f"appearance.traits.{k}" for k in sorted(set(tr_raw) - set(CharacterTraits.model_fields))]
        if unknown:
            conflicts.append(_conflict("UNKNOWN_FIELD", ", ".join(unknown)))

    # ---- ID
    if cid in ctx["library_ids"]:
        conflicts.append(_conflict("ID_NAMESPACE_CONFLICT", f"Library 已有 character_id={cid}"))
    import re

    if not re.fullmatch(ID_PATTERN, cid):
        conflicts.append(_conflict("ID_FORMAT_LEGACY", cid))

    # ---- 名稱
    legacy_name = (cv.display_name.strip() if cv else "") or ""
    name = legacy_name or (script_name or "")
    if legacy_name and script_name and legacy_name != script_name:
        conflicts.append(_conflict("NAME_CONFLICT", f"角色設定「{legacy_name}」≠ 劇本「{script_name}」"))
    if name and ctx["name_counts"].get(name, 0) > 1:
        conflicts.append(_conflict("NAME_CONFLICT", f"本專案有多個角色叫「{name}」"))
    if name and name in ctx["library_names"]:
        conflicts.append(_conflict("NAME_CONFLICT", f"既有 Library 角色同名「{name}」：{sorted(ctx['library_names'][name])}（同名不代表同一角色）"))
    if name:
        mappings.append({"source": "display_name" if legacy_name else "script.characters.name", "target": "display_name",
                         "status": "auto", "value": name})

    # ---- voice
    voice = {"voice_id": cv.voice_id if cv else None, "speed": cv.speed if cv else None, "provider": cv.provider if cv else None,
             "confirmed": cv.confirmed if cv else None}
    narration = bool(usage.get("narration"))
    on_screen = any(usage.get(k) for k in ON_SCREEN)
    has_appearance = cv is not None and cv.appearance is not None and (bool(cv.appearance.anchor_text) or bool(cv.appearance.reference_images)
                                                                       or cv.appearance.seed is not None or bool(cv.appearance.adapter))
    if cv is not None:
        if cv.voice_id not in ("", "default"):
            mappings.append({"source": "voice_id", "target": "voice_profile.voice_id", "status": "auto", "value": cv.voice_id})
        else:
            conflicts.append(_conflict("VOICE_DEFAULT_UNSPECIFIED"))
        if cv.speed is not None:
            mappings.append({"source": "speed", "target": "voice_profile.speed", "status": "auto", "value": cv.speed})
        if cv.confirmed:
            conflicts.append(_conflict("VOICE_CONFIRMATION_REBIND", f"confirmed_at={cv.confirmed_at.isoformat() if cv.confirmed_at else None}"))
    if narration and (on_screen or has_appearance):
        conflicts.append(_conflict("VOICE_ROLE_AMBIGUOUS", "旁白＋畫面角色" if on_screen else "旁白條目帶外觀設定"))

    # ---- appearance
    a = cv.appearance if cv is not None else None
    appearance_out: dict[str, Any] = {}
    if a is not None:
        appearance_out = a.model_dump(mode="json", exclude={"reference_images"})
        for src, dst in _AUTO_APPEARANCE:
            v = getattr(a, src)
            if _nonempty(v):
                mappings.append({"source": f"appearance.{src}", "target": dst, "status": "auto", "value": v})
        if a.description_en.strip():
            mappings.append({"source": "appearance.description_en", "target": None, "status": "human", "value": a.description_en})
            conflicts.append(_conflict("FREE_TEXT_APPEARANCE", "description_en"))
        if [f for f in a.features_en if f.strip()]:
            mappings.append({"source": "appearance.features_en", "target": None, "status": "human", "value": list(a.features_en)})
            conflicts.append(_conflict("FREE_TEXT_APPEARANCE", "features_en"))
        if a.seed is not None:
            legacy_only.append("appearance.seed")
        if a.adapter:
            legacy_only.append("appearance.adapter")
        t = a.traits
        if t is not None:
            for src, dst in _AUTO_TRAITS:
                v = getattr(t, src)
                if _nonempty(v):
                    mappings.append({"source": f"appearance.traits.{src}", "target": dst, "status": "auto", "value": v})
            if t.gender_presentation.strip():
                mappings.append({"source": "appearance.traits.gender_presentation", "target": "gender_presentation",
                                 "status": "human", "value": t.gender_presentation})
                conflicts.append(_conflict("GENDER_MAPPING_AMBIGUOUS", t.gender_presentation))
            if t.age is not None:
                mappings.append({"source": "appearance.traits.age", "target": "age_impression", "status": "human", "value": t.age})
                conflicts.append(_conflict("AGE_MAPPING_AMBIGUOUS", str(t.age)))
            if t.body_type.strip():
                legacy_only.append("appearance.traits.body_type")
        # ---- references
        for raw_path in a.reference_images:
            p = _resolve_ref_path(raw_path, ctx["workspace"])
            ref: dict[str, Any] = {"legacy_path": ctx["sanitize"](raw_path)}
            if not p.is_file():
                ref.update(status="missing", sha256=None)
                conflicts.append(_conflict("REFERENCE_MISSING", ref["legacy_path"]))
            else:
                sha = _bytes_sha(p)
                ctx["ref_file_shas"][raw_path] = sha
                hits = ctx["refs_by_sha"].get(sha, [])
                ref["sha256"] = sha
                ref["library_matches"] = [h["asset_id"] for h in hits]
                bound = sorted({h["character_id"] for h in hits if h["character_id"]})
                if not hits:
                    ref["status"] = "unregistered"
                    conflicts.append(_conflict("REFERENCE_UNREGISTERED", ref["legacy_path"]))
                elif len(hits) > 1 or any(h["problems"] for h in hits):
                    ref["status"] = "conflict"
                    conflicts.append(_conflict("REFERENCE_HASH_CONFLICT", f"sha256 {sha[:12]}… → {[h['asset_id'] for h in hits]}"))
                elif bound:
                    ref["status"] = "bound_to_library_character"
                    ref["library_character_ids"] = bound
                    library_candidates.update(bound)
                else:
                    ref["status"] = "mapped"  # 唯一、無衝突、尚未綁任何角色 → 可提出 binding（dry-run 不寫）
                    proposed_refs.append(hits[0]["asset_id"])
            references.append(ref)
        if legacy_only:
            conflicts.append(_conflict("LEGACY_ONLY_FIELDS", ", ".join(legacy_only)))
    if len(library_candidates) > 1:
        conflicts.append(_conflict("MULTIPLE_LIBRARY_MATCHES", str(sorted(library_candidates))))
    elif len(library_candidates) == 1:
        conflicts.append(_conflict("LIBRARY_MATCH_CANDIDATE", next(iter(library_candidates))))

    # ---- 分類（固定順序規則；見 docs/CHARACTER_LIBRARY_PROJECT_BINDING.md §8.4）
    used = bool(usage)
    cv_data = cv is not None and bool(legacy_name or cv.voice_id not in ("", "default") or cv.speed is not None
                                      or (cv.appearance is not None and cv.appearance != CharacterAppearance()))
    if cv is None:  # 只存在於劇本／Scene 引用
        if script_name:
            conflicts.append(_conflict("SCRIPT_ONLY_CHARACTER", script_name))
        else:
            conflicts.append(_conflict("SCENE_REFERENCE_INCONSISTENT", f"{cid} 不在 Project.characters 也不在劇本"))
    # legacy-only：未被引用，且唯一的資料是模型設定／無對應欄位（seed、adapter、body_type）
    only_legacy = (cv is not None and not used and bool(legacy_only) and not references and not legacy_name
                   and not [m for m in mappings if m["status"] in ("auto", "human")])
    if cv is None:
        pass
    elif not cv_data:
        conflicts.append(_conflict("EMPTY_CHARACTER", f"被引用 {sum(len(v) for v in usage.values())} 處" if used else "未被引用"))
    elif not used and not only_legacy:
        conflicts.append(_conflict("UNUSED_CHARACTER"))
    if narration and not on_screen and not has_appearance and cv is not None:
        conflicts.append(_conflict("NARRATOR_NOT_CHARACTER"))
    if not name and cv_data and not only_legacy and not (narration and not on_screen):
        conflicts.append(_conflict("MISSING_DISPLAY_NAME"))
    if ctx["has_cast"]:
        conflicts.append(_conflict("PROJECT_ALREADY_HAS_CAST"))

    codes = {c["code"] for c in conflicts}
    blocking = sorted({c["code"] for c in conflicts if c["severity"] == "blocking"})
    if cv is not None and "EMPTY_CHARACTER" in codes:
        cls = EMPTY_UNUSED
    elif "NARRATOR_NOT_CHARACTER" in codes and not blocking:
        cls = NARRATOR_SETTING
    elif only_legacy and not blocking:
        cls = LEGACY_ONLY
    elif blocking:
        cls = HUMAN_REQUIRED
    else:
        cls = AUTO_MAPPABLE

    if cls == NARRATOR_SETTING:
        action = "propose_project_narrator_setting"
    elif cls == EMPTY_UNUSED:
        action = "keep_in_legacy_no_library_character"
    elif cls == LEGACY_ONLY:
        action = "keep_in_legacy_only"
    elif library_candidates:
        action = "review_existing_library_candidate"
    elif cls == AUTO_MAPPABLE:
        action = "create_new_library_character"
    else:
        action = "needs_human_decision"

    # ---- 預報：遷移後 anchor 是否會改變（只用 auto 欄位組出候選 CharacterDefinition，不寫入）
    anchor_change = None
    if cls in (AUTO_MAPPABLE, HUMAN_REQUIRED) and name and cv is not None and cv.appearance is not None:
        fields = {m["target"]: m["value"] for m in mappings if m["status"] == "auto" and m["target"] in CharacterDefinition.model_fields
                  and m["target"] not in ("display_name",)}
        try:
            cand = CharacterDefinition(character_id="char_preview", display_name=name, **fields)
            anchor_change = cand.to_appearance().anchor_text != cv.appearance.anchor_text
        except ValueError:
            anchor_change = None

    counts = {k: len(usage.get(k, [])) for k in ("scene_character_ids", "scene_overrides", "gaze_targets", "dialogue", "narration",
                                                   "voice_overrides", "script_characters", "script_beats")}
    rewrites = sorted([w for k in ("scene_character_ids", "scene_overrides", "gaze_targets", "dialogue", "narration",
                                   "script_characters", "script_beats") for w in usage.get(k, [])],
                      key=lambda w: (w.get("scene_id", ""), w["field"]))
    if cv is not None and cls not in (EMPTY_UNUSED, LEGACY_ONLY):  # 保留在 legacy 的條目本身不改寫
        rewrites.append({"field": f"characters[{cid}]"})
    conflicts.sort(key=lambda c: (c["code"], c["detail"]))
    return {
        "legacy_id": cid,
        "source": "project.characters" if cv is not None else ("script" if script_name else "scene_reference_only"),
        "legacy_display_name": legacy_name or None,
        "script_name": script_name,
        "is_narrator_or_voice_only": narration and not on_screen,
        "voice": voice,
        "appearance": appearance_out,
        "references": references,
        "usage_counts": counts,
        "affected_scene_ids": sorted({w["scene_id"] for k in usage for w in usage[k] if "scene_id" in w}),
        "rewrites": rewrites,
        "rewrite_count": len(rewrites),
        "field_mappings": sorted(mappings, key=lambda m: (m["target"] or "", m["source"])),
        "legacy_only_fields": sorted(legacy_only),
        "proposed_action": action,
        "proposed_character_id": PENDING_ID if action == "create_new_library_character" else None,
        "proposed_reference_asset_ids": sorted(proposed_refs),
        "library_candidates": sorted(library_candidates),
        "anchor_text_would_change": anchor_change,
        "classification": cls,
        "confidence": "high" if cls in (AUTO_MAPPABLE, NARRATOR_SETTING, EMPTY_UNUSED, LEGACY_ONLY) else "needs_review",
        "requires_human_decision": cls == HUMAN_REQUIRED or (cls == EMPTY_UNUSED and used),  # 被引用的空條目仍需決定如何處理引用
        "conflicts": conflicts,
    }


# ---------------------------------------------------------------- 主入口
def analyze(project_id: str, workspace: Path) -> dict[str, Any]:
    """產生 dry-run 報告（只讀）。回傳 {"report": …, "report_sha256": …}；時間戳由呼叫端另加，不影響 hash。"""
    from see.core.environment import sanitize
    from see.storage.character_store import CharacterStore
    from see.storage.project_store import ProjectStore

    workspace = Path(workspace)
    pstore = ProjectStore(workspace)
    pfile = pstore.project_file(project_id)
    raw_project = json.loads(pfile.read_text(encoding="utf-8"))
    project = pstore.load(project_id)
    cstore = CharacterStore(workspace)

    lib_state = []
    library_names: dict[str, set[str]] = {}
    for rec in cstore.list(include_archived=True):
        cid = rec.definition.character_id
        revs = cstore.list_revisions(cid)
        head = cstore._path(cid)
        lib_state.append({"character_id": cid, "revision": rec.revision, "archived": rec.archived,
                          "revisions": [{"revision": r, "content_sha256": cstore.read_revision(cid, r).content_sha256} for r in revs],
                          "head_sha256": _bytes_sha(head) if head.is_file() else None})
        library_names.setdefault(rec.definition.display_name.strip(), set()).add(cid)
    refs_by_sha, ref_meta = _ref_index(workspace)

    usage = _usage(project)
    script_names = {c.character_id: c.name for c in (project.script.characters if project.script else [])}
    raw_chars = raw_project.get("characters") or {}
    ids = sorted(set(project.characters) | set(script_names) | set(usage))
    names = [(project.characters[c].display_name.strip() if c in project.characters else "") or script_names.get(c, "") for c in ids]
    ctx = {"workspace": workspace, "library_ids": {x["character_id"] for x in lib_state}, "library_names": library_names,
           "name_counts": {n: names.count(n) for n in set(names) if n}, "refs_by_sha": refs_by_sha, "ref_file_shas": {},
           "has_cast": bool(project.cast), "sanitize": sanitize}
    entries = [_analyze_entry(c, raw_chars.get(c), project.characters.get(c), script_names.get(c), usage.get(c, {}), ctx) for c in ids]

    legacy = [e for e in entries if e["source"] == "project.characters"]
    by_cls = {k: sum(1 for e in entries if e["classification"] == k) for k in CLASSIFICATIONS}
    conflicts = sorted([{**c, "legacy_id": e["legacy_id"]} for e in entries for c in e["conflicts"]],
                       key=lambda c: (c["legacy_id"], c["code"], c["detail"]))
    blocking = [c for c in conflicts if c["severity"] == "blocking"]
    affected = sorted({s for e in entries for s in e["affected_scene_ids"]})
    rewrite_total = sum(e["rewrite_count"] for e in entries)
    not_ready = []
    if blocking:
        not_ready.append(f"{len(blocking)} 個未解決的 blocking conflict")
    need_human = sum(1 for e in entries if e["requires_human_decision"])
    if need_human:
        not_ready.append(f"{need_human} 個角色需要人工決定（本輪沒有人工決定資料）")
    if project.cast:
        not_ready.append("專案已有 Project.cast")
    if not entries:
        not_ready.append("沒有任何角色資料可遷移")
    input_hash = _sha({"project_json": raw_project, "character_library": sorted(lib_state, key=lambda x: x["character_id"]),
                       "reference_library": ref_meta, "legacy_reference_files": dict(sorted(ctx["ref_file_shas"].items()))})
    report = {
        "migration_report_schema_version": MIGRATION_REPORT_SCHEMA_VERSION,
        "kind": "character_migration_dry_run",
        "notice": "Batch 4 only analyzes. No project has been migrated.",
        "project_id": project_id,
        "character_binding_state": "v1_has_cast" if project.cast else "v0_legacy",
        "report_input_hash": input_hash,
        "summary": {
            "total_legacy_characters": len(legacy),
            "total_entries": len(entries),
            "script_or_scene_only": len(entries) - len(legacy),
            "auto_mappable": by_cls[AUTO_MAPPABLE], "human_required": by_cls[HUMAN_REQUIRED], "legacy_only": by_cls[LEGACY_ONLY],
            "narrator_settings": by_cls[NARRATOR_SETTING], "empty_unused": by_cls[EMPTY_UNUSED],
            "affected_scenes": affected, "affected_scene_count": len(affected), "total_rewrite_references": rewrite_total,
            "blocking_conflicts": len(blocking), "migration_ready": not not_ready, "not_ready_reasons": not_ready,
        },
        "entries": entries,
        "conflicts": conflicts,
        "conflict_codes": {k: {"severity": v[0], "message": v[1]} for k, v in CONFLICTS.items()},
        "rules": {"new_id": f"{PENDING_ID}（正式 ID 只在 Batch 5 apply 時由系統產生）",
                  "library_matching": "只接受唯一的 reference sha256 證據且仍需人工確認；不以名稱、性別或外觀文字判定同一角色",
                  "relative_reference_paths": "相對 workspace 上層（repo 根）解析"},
    }
    return {"report": report, "report_sha256": _sha(report)}


# ---------------------------------------------------------------- zero-write proof
def workspace_digest(workspace: Path) -> str:
    """整個 workspace 的內容指紋：檔案路徑＋大小＋sha256（媒體檔用大小＋mtime_ns 以免過慢）。"""
    ws = Path(workspace)
    items = []
    if ws.is_dir():
        for root, _dirs, files in os.walk(ws):
            for f in files:
                p = Path(root) / f
                st = p.stat()
                rel = p.relative_to(ws).as_posix()
                if p.suffix.lower() in (".json", ".txt", ".srt", ".ass"):
                    items.append((rel, st.st_size, _bytes_sha(p)))
                else:
                    items.append((rel, st.st_size, st.st_mtime_ns))
    return _sha(sorted(items))


def human_summary(result: dict[str, Any]) -> str:
    r = result["report"]
    s = r["summary"]
    zh = {AUTO_MAPPABLE: "可自動對應", HUMAN_REQUIRED: "需人工決定", LEGACY_ONLY: "只保留舊資料", NARRATOR_SETTING: "旁白設定",
          EMPTY_UNUSED: "空白／未使用"}
    lines = [f"角色遷移 dry-run（只分析，未遷移任何資料）— 專案 {r['project_id']}",
             f"舊角色設定 {s['total_legacy_characters']} 個；劇本／Scene 另引用 {s['script_or_scene_only']} 個",
             f"可自動對應 {s['auto_mappable']}｜需人工決定 {s['human_required']}｜只保留舊資料 {s['legacy_only']}｜"
             f"旁白設定 {s['narrator_settings']}｜空白／未使用 {s['empty_unused']}",
             f"受影響場景 {s['affected_scene_count']} 個；需改寫引用 {s['total_rewrite_references']} 處；blocking 衝突 {s['blocking_conflicts']} 個",
             f"可以遷移：{'是' if s['migration_ready'] else '否'}" + (f"（{'；'.join(s['not_ready_reasons'])}）" if s["not_ready_reasons"] else ""),
             "---"]
    for e in r["entries"]:
        name = e["legacy_display_name"] or e["script_name"] or "（無名稱）"
        lines.append(f"• {e['legacy_id']}「{name}」→ {zh[e['classification']]}；建議：{e['proposed_action']}；"
                     f"引用 {e['rewrite_count']} 處（場景 {len(e['affected_scene_ids'])}）")
        for c in e["conflicts"]:
            lines.append(f"    [{c['severity']}] {c['code']}：{c['message']}" + (f"（{c['detail']}）" if c["detail"] else ""))
    lines.append(f"report_input_hash {r['report_input_hash']}")
    lines.append(f"report_sha256     {result['report_sha256']}")
    return "\n".join(lines)
