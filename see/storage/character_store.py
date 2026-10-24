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


class CharacterRecord(BaseModel):
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

    def get(self, character_id: str) -> CharacterRecord:
        p = self._path(character_id)
        if not p.is_file():
            raise KeyError(character_id)
        return CharacterRecord.model_validate_json(p.read_text(encoding="utf-8"))

    def list(self, include_archived: bool = False) -> list[CharacterRecord]:
        if not self.root.is_dir():
            return []
        recs = [CharacterRecord.model_validate_json(p.read_text(encoding="utf-8")) for p in sorted(self.root.glob("*.json"))]
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
