"""Project cast resolver（D-068 Batch 3）：把 `Project.cast` 的 pinned binding 解析成 Library revision snapshot（唯讀）。

D-073 Batch 6A：production 只經 `see/core/character_source.py`（committed migration＋cast 一致時）間接使用本 resolver；
本模組本身仍只做唯讀解析（readiness／檢查／匯出／production source）。

規則：只讀 pinned revision；不 fallback latest；revision 缺失／hash 不符 → integrity=error（fail closed）；
reference 遺失 → generation_ready=False；archived 角色的歷史 revision 仍可解析；不自動換角色、不寫任何檔案。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from see.models.character_binding import CharacterBinding, resolve_binding


@dataclass
class CastEntry:
    binding: CharacterBinding
    integrity: str  # ok｜error
    resolved_revision: int | None = None
    content_sha256: str | None = None
    archived: bool | None = None
    generation_ready: bool = False
    missing_references: list[str] = field(default_factory=list)
    snapshot: dict[str, Any] | None = None  # 解析到的 CharacterDefinition（JSON）
    error: str = ""

    def to_dict(self, include_snapshot: bool = True) -> dict[str, Any]:
        d = {"binding": self.binding.model_dump(mode="json"), "integrity": self.integrity, "resolved_revision": self.resolved_revision,
             "content_sha256": self.content_sha256, "archived": self.archived, "generation_ready": self.generation_ready,
             "missing_references": list(self.missing_references), "error": self.error}
        if include_snapshot:
            d["snapshot"] = self.snapshot
        return d


@dataclass
class CastReport:
    status: str  # not_configured｜ok｜partial（可解析但有不可生成）｜error（有 revision 解析失敗）
    entries: list[CastEntry]

    @property
    def generation_ready(self) -> bool:
        return self.status == "ok"

    def to_dict(self, include_snapshot: bool = True) -> dict[str, Any]:
        return {"status": self.status, "generation_ready": self.generation_ready,
                "entries": [e.to_dict(include_snapshot) for e in self.entries]}


def resolve_project_cast(project, character_store, reference_library=None) -> CastReport:
    """逐筆解析 `project.cast`。單筆失敗不影響其他筆的解析結果，但整體狀態取最差者。"""
    from see.storage.character_store import CharacterStoreError

    if not project.cast:
        return CastReport(status="not_configured", entries=[])
    entries: list[CastEntry] = []
    for b in project.cast:
        try:
            r = resolve_binding(character_store, b, reference_library)
        except CharacterStoreError as e:  # 含 CharacterRevisionError：缺失、hash 不符、版本過新 → fail closed
            entries.append(CastEntry(binding=b, integrity="error", error=str(e)))
            continue
        rev = r.revision
        entries.append(CastEntry(binding=b, integrity="ok", resolved_revision=rev.revision, content_sha256=rev.content_sha256,
                                 archived=rev.archived, generation_ready=r.generation_ready, missing_references=list(r.missing_assets),
                                 snapshot=rev.definition.model_dump(mode="json"),
                                 error="; ".join(r.issues)))
    if any(e.integrity == "error" for e in entries):
        status = "error"
    elif all(e.generation_ready for e in entries):
        status = "ok"
    else:
        status = "partial"
    return CastReport(status=status, entries=entries)
