"""CharacterBinding（D-067；revision pinning 的基礎 contract）：Project 未來用 `character_id + character_revision` 綁定 Library 角色。

**尚未接進 production Project**（不改 Project.characters、不做 migration；Batch 3 起才接）。
可重現性保證（測試證明）：pin 在 `char_x@3`，即使 Library 已到 revision 7，解析結果仍是 revision 3；
revision 不存在或 hash 不符 → fail closed（CharacterRevisionError），**絕不 fallback 到 latest**。
「跟隨最新版」未來若要做，只能是顯式 opt-in（需另行實作與裁示；本 model 只允許 pinned）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 與 see.models.character_definition.ID_PATTERN 相同（測試保證一致）；這裡不匯入，避免 Project ↔ character_definition 循環匯入
ID_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"
CAST_SCHEMA_VERSION = 1


class CharacterBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: str = Field(pattern=ID_PATTERN)
    character_revision: int = Field(ge=1, description="鎖定的 Library revision（預設行為；不自動更新）")
    role_label: str = Field(default="", max_length=40, description="本專案角色標籤，例 男主角／店長／路人")
    alias: str = Field(default="", max_length=64, description="本專案顯示別名（選填；不改 Library display_name）")
    follow: Literal["pinned"] = Field(default="pinned", description="目前只允許 pinned；跟隨最新版需另行顯式 opt-in 設計")


@dataclass
class ResolvedCharacter:
    """pinned revision 的解析結果。revision 本身可讀不代表可以生成：reference 遺失 → generation_ready=False。"""

    binding: CharacterBinding
    revision: object  # CharacterRevision（避免 models ↔ storage 循環匯入）
    generation_ready: bool
    missing_assets: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def resolve_binding(store, binding: CharacterBinding, library=None) -> ResolvedCharacter:
    """讀 binding 指定的 revision（不是 latest），並檢查其凍結的 reference 目前是否仍在且 sha256 相同。
    - revision 缺失／hash 不符 → 由 store.read_revision 丟 CharacterRevisionError（fail closed）。
    - reference 遺失或內容改變 → generation_ready=False、列出 missing／changed；**不改綁其他圖**。"""
    from see.core.hashing import file_sha256
    from see.core.reference_library import ReferenceLibrary, ReferenceLibraryError

    rev = store.read_revision(binding.character_id, binding.character_revision)
    lib = library or ReferenceLibrary(store.workspace)
    missing: list[str] = []
    issues: list[str] = []
    for b in rev.reference_bindings:
        if b.status != "ok" or not b.rel_path or not b.sha256:
            missing.append(b.asset_id)
            issues.append(f"{b.asset_id}: revision 記錄時即為 {b.status}")
            continue
        try:
            p = lib._resolve(b.rel_path)
        except ReferenceLibraryError as e:
            missing.append(b.asset_id)
            issues.append(f"{b.asset_id}: {e}")
            continue
        if not p.is_file():
            missing.append(b.asset_id)
            issues.append(f"{b.asset_id}: 檔案不存在（{b.rel_path}）")
        elif file_sha256(p) != b.sha256:
            missing.append(b.asset_id)
            issues.append(f"{b.asset_id}: 檔案內容已改變（sha256 與 revision {rev.revision} 記錄不符）")
    return ResolvedCharacter(binding=binding, revision=rev, generation_ready=not missing, missing_assets=missing, issues=issues)
