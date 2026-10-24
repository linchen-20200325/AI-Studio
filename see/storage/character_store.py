"""Character Library 持久化（D-058 §17.1；D-062 Batch C）：`workspace/character_library/<character_id>.json`（不進 Git）。

- create／read／update／archive（停用）／restore；**沒有 hard delete**（不可逆刪除需另經裁示）。
- 每次 update 遞增 revision、保留 created_at；檔案寫入採暫存檔＋rename（中斷不留下半個 JSON）。
- 尚未與 `Project.characters`（CharacterVoice）綁定或遷移：專案如何引用 Character Library 待裁示（BACKLOG）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from see.models.character_definition import CharacterDefinition


def _now() -> datetime:
    return datetime.now(timezone.utc)


CHARACTER_SCHEMA_VERSION = 1  # D-064：未來 schema 變更 → 先 backup()；不可逆遷移 → Decision Gate


class CharacterRecord(BaseModel):
    schema_version: int = Field(default=CHARACTER_SCHEMA_VERSION, ge=1, description="舊檔沒有此欄位 → 視為 v1")
    definition: CharacterDefinition
    archived: bool = False
    revision: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class CharacterStoreError(ValueError):
    pass


class CharacterStore:
    def __init__(self, workspace: Path) -> None:
        self.root = Path(workspace) / "character_library"

    def _path(self, character_id: str) -> Path:
        import re

        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", character_id):  # 同 schema ID_PATTERN；防路徑注入
            raise CharacterStoreError(f"invalid character_id: {character_id!r}")
        return self.root / f"{character_id}.json"

    def _save(self, rec: CharacterRecord) -> CharacterRecord:
        self.root.mkdir(parents=True, exist_ok=True)
        p = self._path(rec.definition.character_id)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(rec.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(p)
        return rec

    def create(self, definition: CharacterDefinition) -> CharacterRecord:
        if self._path(definition.character_id).exists():
            raise CharacterStoreError(f"character_id already exists: {definition.character_id}")
        return self._save(CharacterRecord(definition=definition))

    @staticmethod
    def _load(p: Path) -> CharacterRecord:
        """讀檔；比程式新的 schema → fail safe（不猜、不改寫）。"""
        rec = CharacterRecord.model_validate_json(p.read_text(encoding="utf-8"))
        if rec.schema_version > CHARACTER_SCHEMA_VERSION:
            raise CharacterStoreError(f"{p.name}: schema_version {rec.schema_version} is newer than supported "
                                      f"{CHARACTER_SCHEMA_VERSION}; update the program instead of editing")
        return rec

    def get(self, character_id: str) -> CharacterRecord:
        p = self._path(character_id)
        if not p.is_file():
            raise KeyError(character_id)
        return self._load(p)

    def backup(self, dest_root: Path | None = None) -> Path:
        """遷移前備份（D-064）：整份 character_library 複製到 workspace/backups/character_library-<時間>/；不改原檔。"""
        import shutil

        stamp = _now().strftime("%Y%m%dT%H%M%S%fZ")
        dest = Path(dest_root or self.root.parent / "backups") / f"character_library-{stamp}"
        if self.root.is_dir():
            shutil.copytree(self.root, dest)
        else:
            dest.mkdir(parents=True)
        return dest

    def migration_plan(self) -> dict[str, list[str]]:
        """列出需要遷移的檔案（只讀）。目前只有 v1：舊檔（無 schema_version）以 v1 相容讀取，**不重寫**。"""
        plan: dict[str, list[str]] = {"current": [], "legacy_compatible": [], "newer_than_supported": [], "unreadable": []}
        for p in sorted(self.root.glob("*.json")) if self.root.is_dir() else []:
            try:
                import json

                raw = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                plan["unreadable"].append(p.name)
                continue
            v = raw.get("schema_version")
            key = ("legacy_compatible" if v is None else "current" if v == CHARACTER_SCHEMA_VERSION
                   else "newer_than_supported" if isinstance(v, int) and v > CHARACTER_SCHEMA_VERSION else "unreadable")
            plan[key].append(p.name)
        return plan

    def list(self, include_archived: bool = False) -> list[CharacterRecord]:
        if not self.root.is_dir():
            return []
        recs = [self._load(p) for p in sorted(self.root.glob("*.json"))]
        return [r for r in recs if include_archived or not r.archived]

    def update(self, character_id: str, /, **changes: object) -> CharacterRecord:
        """部分更新定義欄位（character_id 不可改：它是穩定身份鍵）。封存中的角色不可修改。"""
        rec = self.get(character_id)
        if rec.archived:
            raise CharacterStoreError(f"{character_id} is archived; restore it before editing")
        if "character_id" in changes and changes["character_id"] != character_id:
            raise CharacterStoreError("character_id is a stable identity key and cannot be changed")
        data = {**rec.definition.model_dump(), **{k: v for k, v in changes.items() if k != "character_id"}}
        definition = CharacterDefinition.model_validate(data)
        if definition == rec.definition:
            return rec
        return self._save(rec.model_copy(update={"definition": definition, "revision": rec.revision + 1, "updated_at": _now()}))

    def archive(self, character_id: str) -> CharacterRecord:
        rec = self.get(character_id)
        return rec if rec.archived else self._save(rec.model_copy(update={"archived": True, "revision": rec.revision + 1, "updated_at": _now()}))

    def restore(self, character_id: str) -> CharacterRecord:
        rec = self.get(character_id)
        return rec if not rec.archived else self._save(rec.model_copy(update={"archived": False, "revision": rec.revision + 1, "updated_at": _now()}))
