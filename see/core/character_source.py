"""Production character source（D-073 Batch 6A）：production 讀角色資料的**唯一**邊界。

- **cast 模式**：專案有 Project.cast，且 workspace 有一筆 committed migration record，其 cast（character_id＋character_revision＋
  content_sha256）與 Project.cast 完全一致 → 只用 pinned revision（經 `resolve_project_cast()`）。`Project.characters` 不再被讀取。
- **legacy 模式**：專案沒有 cast，且沒有 committed／committing migration record → 完全沿用 `Project.characters`（行為與 fingerprint 不變）。
- 其餘一律 **fail closed**（CharacterSourceError），**不 fallback `Project.characters`、不 fallback latest revision**：
  cast 有但沒有 committed record、record 與 cast 不一致、committing／無法讀取的 record、revision 缺失／hash 不符、
  reference 遺失、Scene 引用不在 cast 的 ID、cast 為空卻有 committed record。
- 不補值：definition 沒有 voice_profile → voice 為 provider 預設（與 legacy `voice_id="default"` 同語意），speed 為 None（沿用 project）。

未處理（BACKLOG）：cast 角色的 voice 人工確認（沒有 schema → cast 模式的旁白角色一律視為未確認，Final 被擋）、
`narrator_setting`、legacy Project.characters 條目的 migration、Audio architecture。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from see.core.errors import SchemaViolation

LEGACY = "legacy_project_characters"
CAST = "pinned_project_cast"


class CharacterSourceError(SchemaViolation):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CastCharacter:
    character_id: str
    character_revision: int
    content_sha256: str
    display_name: str
    anchor_text: str
    voice_id: str | None
    speed: float | None


@dataclass
class CharacterSource:
    mode: str  # LEGACY｜CAST
    project: Any
    cast: dict[str, CastCharacter] = field(default_factory=dict)
    migration_id: str | None = None

    # ---- image（anchor 文字錨點；legacy 結構與 fingerprint 完全不變）
    def image_ref(self, cid: str, scene_id: str) -> dict[str, Any] | None:
        if self.mode == LEGACY:
            ch = self.project.characters.get(cid)
            if ch is not None and ch.appearance is not None and ch.appearance.anchor_text:
                a = ch.appearance
                return {"character_id": cid, "anchor": a.anchor_text, "reference_images": list(a.reference_images),
                        "seed": a.seed, "adapter": dict(a.adapter)}
            return None
        c = self._get(cid, scene_id, "character_ids")
        if not c.anchor_text:
            return None
        return {"character_id": cid, "character_revision": c.character_revision, "content_sha256": c.content_sha256,
                "anchor": c.anchor_text}

    # ---- voice（narrator）
    def narrator_voice(self, narrator_id: str, scene_id: str) -> tuple[str | None, float | None, str]:
        """回傳 (voice_id 或 None＝未指定, speed 或 None, source label)。"""
        if self.mode == LEGACY:
            ch = self.project.characters.get(narrator_id)
            if ch is None:
                raise SchemaViolation(f"scene {scene_id}: narrator_id '{narrator_id}' not in project.characters")
            return ch.voice_id, ch.speed, f"character:{ch.character_id}"
        c = self._get(narrator_id, scene_id, "narrator_id")
        return c.voice_id, c.speed, f"cast:{c.character_id}@r{c.character_revision}"

    def known_ids(self) -> set[str]:
        return set(self.project.characters) if self.mode == LEGACY else set(self.cast)

    def unconfirmed(self) -> list[str]:
        used = {s.narrator_id for s in self.project.scenes if s.narrator_id}
        if self.mode == LEGACY:
            ch = self.project.characters
            return sorted(c for c in used if c in ch and not ch[c].confirmed)
        # cast 模式：尚無 cast 層 voice 確認 schema（BACKLOG）→ 被當旁白的 cast 角色一律未確認（fail closed，不沿用 legacy confirmed）
        return sorted(c for c in used if c in self.cast)

    def _get(self, cid: str, scene_id: str, where: str) -> CastCharacter:
        c = self.cast.get(cid)
        if c is None:
            raise CharacterSourceError("CAST_REFERENCE_NOT_IN_CAST", f"scene {scene_id} {where}: '{cid}' 不在 Project.cast（不 fallback Project.characters）")
        return c


def _records(ws: Path, pid: str) -> list[dict[str, Any]]:
    d = Path(ws) / "migrations" / pid
    out = []
    for p in sorted(d.glob("mig_*.json")) if d.is_dir() else []:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            out.append({"migration_id": p.stem, "status": "unreadable"})
    return out


def resolve_character_source(project: Any, workspace: Path) -> CharacterSource:
    """判斷 production 角色來源並解析（唯讀）。不一致 → CharacterSourceError。"""
    recs = _records(workspace, project.project_id)
    bad = [r for r in recs if r.get("status") in ("committing", "unreadable")]
    if bad:
        raise CharacterSourceError("MIGRATION_RECORD_INCOMPLETE", ", ".join(f"{r.get('migration_id')}={r.get('status')}" for r in bad))
    committed = [r for r in recs if r.get("status") == "committed"]
    if not project.cast:
        if committed:
            raise CharacterSourceError("CAST_MIGRATION_STATE_INCONSISTENT",
                                       f"有 committed migration {[r.get('migration_id') for r in committed]} 但 Project.cast 為空")
        return CharacterSource(mode=LEGACY, project=project)
    if len(committed) != 1:
        raise CharacterSourceError("CAST_MIGRATION_STATE_INCONSISTENT",
                                   f"Project.cast 存在但 committed migration record 數＝{len(committed)}（需剛好 1 筆）")
    rec = committed[0]
    want = {(c["character_id"], c["character_revision"]): c.get("content_sha256") for c in rec.get("cast", [])}
    have = {(b.character_id, b.character_revision) for b in project.cast}
    if set(want) != have:
        raise CharacterSourceError("CAST_MIGRATION_STATE_INCONSISTENT",
                                   f"Project.cast {sorted(have)} ≠ migration {rec.get('migration_id')} 的 cast {sorted(want)}")
    from see.core.cast import resolve_project_cast
    from see.storage.character_store import CharacterStore

    rep = resolve_project_cast(project, CharacterStore(workspace))
    errs = [f"{e.binding.character_id}@{e.binding.character_revision}: {e.error}" for e in rep.entries if e.integrity != "ok"]
    if errs:
        raise CharacterSourceError("CAST_RESOLUTION_FAILED", "; ".join(errs))
    missing = [f"{e.binding.character_id}: {e.missing_references}" for e in rep.entries if not e.generation_ready]
    if missing:
        raise CharacterSourceError("CAST_REFERENCE_MISSING", "; ".join(missing))
    from see.models.character_definition import CharacterDefinition

    cast: dict[str, CastCharacter] = {}
    for e in rep.entries:
        b = e.binding
        if want[(b.character_id, b.character_revision)] != e.content_sha256:
            raise CharacterSourceError("CAST_RESOLUTION_FAILED", f"{b.character_id}@{b.character_revision}: content_sha256 與 migration record 不符")
        d = CharacterDefinition.model_validate(e.snapshot)
        vp = d.voice_profile
        cast[b.character_id] = CastCharacter(character_id=b.character_id, character_revision=b.character_revision,
                                             content_sha256=e.content_sha256, display_name=d.display_name,
                                             anchor_text=d.to_appearance().anchor_text,
                                             voice_id=vp.voice_id if vp else None, speed=vp.speed if vp else None)
    return CharacterSource(mode=CAST, project=project, cast=cast, migration_id=rec.get("migration_id"))
