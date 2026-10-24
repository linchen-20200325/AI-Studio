"""Reference Library service（D-058 §17.3；D-062 Batch C）：列出／登記／驗證 reference metadata、綁定角色、主要 reference。

- 圖片只在本機 `workspace/reference_library/<category>/`（workspace/ 已 gitignore）；本模組只讀寫 sidecar metadata
  `<檔名>.ref.json`（ReferenceAsset），**從不複製、搬移或刪除圖片**。
- 舊 `workspace/identity_refs/` 為 legacy：只列出、不登記、不改寫（唯讀相容）。
- 歸屬與用途只看 metadata；檔名與資料夾不推論身份（PROJECT_RULES §17）。任何不一致 → fail closed（ReferenceLibraryError）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from see.core.hashing import file_sha256
from see.models.character_definition import (CHARACTER_ROLES, ROLE_CATEGORIES, RefCategory, ReferenceAsset, RefRole,
                                             support_status)

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
SIDECAR_SUFFIX = ".ref.json"


class ReferenceLibraryError(ValueError):
    """metadata 衝突或不安全操作（fail closed）。"""


@dataclass(frozen=True)
class LibraryEntry:
    rel_path: str  # 相對 Library 根，例 people/hero_v1.jpg
    category: str
    legacy: bool
    asset: ReferenceAsset | None  # None＝尚未登記 metadata
    problems: tuple[str, ...]  # 驗證問題（空＝一致）

    @property
    def support(self) -> str:
        if self.asset is None:
            return "unregistered"
        return support_status(self.asset.category, self.asset.role)


class ReferenceLibrary:
    def __init__(self, workspace: Path) -> None:
        self.root = Path(workspace) / "reference_library"
        self.legacy_root = Path(workspace) / "identity_refs"

    # ------------------------------------------------------------ 路徑
    def _resolve(self, rel_path: str, *, legacy: bool = False) -> Path:
        root = self.legacy_root if legacy else self.root
        rel = Path(rel_path)
        if rel.is_absolute() or ".." in rel.parts or len(rel.parts) != 2:
            raise ReferenceLibraryError(f"path must be <category>/<file> inside the library: {rel_path}")
        if rel.parts[0] not in {c.value for c in RefCategory}:
            raise ReferenceLibraryError(f"unknown category '{rel.parts[0]}'; known: {[c.value for c in RefCategory]}")
        if rel.suffix.lower() not in IMAGE_SUFFIXES:
            raise ReferenceLibraryError(f"unsupported image type: {rel.suffix}")
        p = (root / rel).resolve()
        if not p.is_relative_to(root.resolve()):
            raise ReferenceLibraryError(f"path escapes the library: {rel_path}")
        return p

    @staticmethod
    def sidecar(image: Path) -> Path:
        return image.with_name(image.name + SIDECAR_SUFFIX)

    # ------------------------------------------------------------ 讀取
    def read_asset(self, image: Path) -> ReferenceAsset | None:
        side = self.sidecar(image)
        if not side.is_file():
            return None
        try:
            return ReferenceAsset.model_validate_json(side.read_text(encoding="utf-8"))
        except ValueError as e:
            raise ReferenceLibraryError(f"invalid metadata {side.name}: {e}") from e

    def validate(self, image: Path, asset: ReferenceAsset, category: str) -> list[str]:
        """metadata 與實際檔案／所在類別是否一致（不一致即問題，呼叫端 fail closed）。"""
        problems = []
        if not image.is_file():
            problems.append("image file missing")
        elif file_sha256(image) != asset.sha256:
            problems.append("sha256 mismatch (file changed after registration)")
        if asset.category.value != category:
            problems.append(f"metadata category {asset.category.value} != folder {category}")
        if Path(asset.file_path).name != image.name:
            problems.append(f"metadata file_path {asset.file_path} does not point to {image.name}")
        if asset.category not in ROLE_CATEGORIES[asset.role]:
            problems.append(f"role {asset.role.value} not allowed in category {asset.category.value}")
        if asset.role in CHARACTER_ROLES and asset.is_primary and asset.character_id is None:
            problems.append("primary reference must be bound to a character")
        return problems

    def list(self, category: str | None = None, include_legacy: bool = True) -> list[LibraryEntry]:
        out: list[LibraryEntry] = []
        for root, legacy in ((self.root, False), (self.legacy_root, True)):
            if legacy and not include_legacy or not root.is_dir():
                continue
            for cat_dir in sorted(p for p in root.iterdir() if p.is_dir()):
                if category and cat_dir.name != category:
                    continue
                for img in sorted(p for p in cat_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES):
                    try:
                        asset = self.read_asset(img)
                        problems = tuple(self.validate(img, asset, cat_dir.name)) if asset else ()
                    except ReferenceLibraryError as e:
                        asset, problems = None, (str(e),)
                    out.append(LibraryEntry(f"{cat_dir.name}/{img.name}", cat_dir.name, legacy, asset, problems))
        return out

    def get(self, asset_id: str) -> tuple[Path, ReferenceAsset]:
        hits = [(self._resolve(e.rel_path), e.asset) for e in self.list(include_legacy=False)
                if e.asset is not None and e.asset.asset_id == asset_id]
        if len(hits) != 1:
            raise ReferenceLibraryError(f"asset_id '{asset_id}' matched {len(hits)} entries (need exactly 1)")
        return hits[0]

    # ------------------------------------------------------------ 寫入（只寫 sidecar）
    def _write(self, image: Path, asset: ReferenceAsset) -> ReferenceAsset:
        problems = self.validate(image, asset, image.parent.name)
        if problems:
            raise ReferenceLibraryError("; ".join(problems))
        self.sidecar(image).write_text(asset.model_dump_json(indent=2), encoding="utf-8")
        return asset

    def register(self, rel_path: str, *, asset_id: str, role: RefRole, source_type: str, character_id: str | None = None,
                 provenance: dict | None = None, commercial_clearance_status: str = "unknown", notes: str = "",
                 overwrite: bool = False) -> ReferenceAsset:
        """登記一張已放在主 Library 的圖片（計算 sha256、寫 metadata）。legacy 路徑不可登記。"""
        image = self._resolve(rel_path)
        if not image.is_file():
            raise ReferenceLibraryError(f"image not found in library: {rel_path}")
        if self.sidecar(image).exists() and not overwrite:
            raise ReferenceLibraryError(f"already registered: {rel_path} (use overwrite)")
        if any(e.asset and e.asset.asset_id == asset_id and e.rel_path != rel_path for e in self.list(include_legacy=False)):
            raise ReferenceLibraryError(f"asset_id already used: {asset_id}")
        prov = {"registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **(provenance or {})}
        asset = ReferenceAsset(asset_id=asset_id, category=image.parent.name, file_path=str(image), character_id=character_id,
                               role=role, sha256=file_sha256(image), source_type=source_type, provenance=prov,
                               commercial_clearance_status=commercial_clearance_status, notes=notes)
        return self._write(image, asset)

    def bind(self, asset_id: str, character_id: str | None) -> ReferenceAsset:
        """綁定／解除綁定角色（解除時一併取消 primary）。"""
        image, asset = self.get(asset_id)
        data = asset.model_dump()
        data["character_id"] = character_id
        if character_id is None:
            data["is_primary"] = False
        return self._write(image, ReferenceAsset.model_validate(data))

    def mark_primary(self, asset_id: str) -> ReferenceAsset:
        """指定某角色的主要 identity reference；同角色其他 identity_face 自動取消 primary。"""
        image, asset = self.get(asset_id)
        if asset.character_id is None or asset.role != RefRole.identity_face:
            raise ReferenceLibraryError("primary reference must be an identity_face bound to a character")
        for e in self.list(include_legacy=False):
            a = e.asset
            if a and a.asset_id != asset_id and a.character_id == asset.character_id and a.role == RefRole.identity_face and a.is_primary:
                self._write(self._resolve(e.rel_path), a.model_copy(update={"is_primary": False}))
        return self._write(image, asset.model_copy(update={"is_primary": True}))

    def assets_for(self, character_id: str) -> list[ReferenceAsset]:
        return [e.asset for e in self.list(include_legacy=False) if e.asset and e.asset.character_id == character_id and not e.problems]


def entries_json(entries: list[LibraryEntry]) -> str:
    return json.dumps([{"path": e.rel_path, "category": e.category, "legacy": e.legacy, "support": e.support,
                        "problems": list(e.problems), "asset": e.asset.model_dump(mode="json") if e.asset else None}
                       for e in entries], ensure_ascii=False, indent=2)
