"""Character Library 持久化（D-058 §17.1；D-062 Batch C；D-067 Batch 2 不可變 revision history）。不進 Git。

佈局（workspace/character_library/）：
- `<character_id>.json`：head（CharacterRecord；目前狀態的**索引**，相容舊版讀取）。
- `history/<character_id>/r000001.json`…：**append-only 不可變 revision**（CharacterRevision）。歷史的唯一來源；
  以 exclusive create 寫入（同號已存在 → 拒絕），永不覆寫、永不刪除。

規則：
- create／update／rename（update display_name）／archive／restore／refresh_references 每次「有效修改」都產生下一個 revision
  （單調遞增）；沒有實際變更 → 不產生 revision。**沒有 hard delete、沒有修改舊 revision 的 API。**
- 每個 revision 帶 canonical `content_sha256`；讀取時重算，不符 → CharacterRevisionError（fail closed，不自動修復）。
- revision 凍結當時的 reference metadata（asset_id、role、`<category>/<file>`、sha256、primary）；不含本機絕對路徑。
- **legacy**：D-067 之前建立、沒有 history 的角色，第一次在新版修改前，把「當下可證明的 head」寫成 baseline revision
  （同 revision 號，`baseline_from_legacy_current=true`）；更早的 revision 不存在、不倒推、不補造。
- 新角色用 `create_new()`：character_id 由系統產生（`char_`＋12 位小寫 hex，標準庫 secrets；不由 display_name 產生），
  rename 不改 ID（DG-29 裁示 A）。`create(definition)` 保留給既有 ID 的匯入／測試。
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from see.models.character_definition import ID_PATTERN, CharacterDefinition, RefRole


def _now() -> datetime:
    return datetime.now(timezone.utc)


CHARACTER_SCHEMA_VERSION = 1  # head 檔（D-064）：未來 schema 變更 → 先 backup()；不可逆遷移 → Decision Gate
REVISION_SCHEMA_VERSION = 1  # history revision 檔（D-067）
HISTORY_DIR = "history"
REV_NAME = re.compile(r"^r(\d{6,})\.json$")


class CharacterRecord(BaseModel):
    schema_version: int = Field(default=CHARACTER_SCHEMA_VERSION, ge=1, description="舊檔沒有此欄位 → 視為 v1")
    definition: CharacterDefinition
    archived: bool = False
    revision: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class ReferenceBinding(BaseModel):
    """revision 凍結的一筆 reference metadata（只有可攜資料：asset_id、相對路徑、sha256）。"""

    asset_id: str
    status: str = Field(description="ok｜missing（Library 找不到此 asset_id）｜inconsistent（metadata 與檔案不一致）")
    role: str | None = None
    category: str | None = None
    rel_path: str | None = Field(default=None, description="<category>/<file>（相對 Reference Library 根）")
    sha256: str | None = Field(default=None, description="登記時的 sha256（metadata 值；missing 時為 None，不補造）")
    is_primary: bool = False
    problems: list[str] = Field(default_factory=list)


class CharacterRevision(BaseModel):
    schema_version: int = Field(default=REVISION_SCHEMA_VERSION, ge=1)
    character_id: str = Field(pattern=ID_PATTERN)
    revision: int = Field(ge=1)
    created_at: datetime
    archived: bool
    definition: CharacterDefinition
    reference_asset_ids: list[str] = Field(default_factory=list, description="本 revision 綁定的 reference（排序後）")
    primary_reference_asset_id: str | None = None
    reference_bindings: list[ReferenceBinding] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict, description="action、previous_revision、baseline_from_legacy_current、note")
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def hash_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"content_sha256"})


class CharacterStoreError(ValueError):
    pass


class CharacterRevisionError(CharacterStoreError):
    """revision 遺失、hash 不符或版本過新（fail closed）。"""


def canonical_hash(payload: dict[str, Any]) -> str:
    """確定性 hash：key 排序、無多餘空白、UTF-8；同樣資料 → 同樣 hash，dict 欄位順序不影響。"""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def new_character_id() -> str:
    """系統產生的穩定 ID（符合 ID_PATTERN；不含名稱資訊）。"""
    return f"char_{secrets.token_hex(6)}"


class CharacterStore:
    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)
        self.root = self.workspace / "character_library"

    # ------------------------------------------------------------ 路徑
    def _path(self, character_id: str) -> Path:
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", character_id):  # 同 schema ID_PATTERN；防路徑注入
            raise CharacterStoreError(f"invalid character_id: {character_id!r}")
        return self.root / f"{character_id}.json"

    def _history_dir(self, character_id: str) -> Path:
        self._path(character_id)
        return self.root / HISTORY_DIR / character_id

    def _rev_path(self, character_id: str, revision: int) -> Path:
        return self._history_dir(character_id) / f"r{revision:06d}.json"

    # ------------------------------------------------------------ head（索引）
    def _save_head(self, rec: CharacterRecord) -> CharacterRecord:
        self.root.mkdir(parents=True, exist_ok=True)
        p = self._path(rec.definition.character_id)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(rec.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(p)
        return rec

    @staticmethod
    def _load(p: Path) -> CharacterRecord:
        """讀 head；比程式新的 schema → fail safe（不猜、不改寫）。"""
        rec = CharacterRecord.model_validate_json(p.read_text(encoding="utf-8"))
        if rec.schema_version > CHARACTER_SCHEMA_VERSION:
            raise CharacterStoreError(f"{p.name}: schema_version {rec.schema_version} is newer than supported "
                                      f"{CHARACTER_SCHEMA_VERSION}; update the program instead of editing")
        return rec

    def _head(self, character_id: str) -> CharacterRecord:
        p = self._path(character_id)
        if not p.is_file():
            raise KeyError(character_id)
        return self._load(p)

    # ------------------------------------------------------------ revision history（唯讀 API）
    def list_revisions(self, character_id: str) -> list[int]:
        d = self._history_dir(character_id)
        if not d.is_dir():
            return []
        return sorted(int(m.group(1)) for p in d.iterdir() if (m := REV_NAME.match(p.name)))

    def has_history(self, character_id: str) -> bool:
        return bool(self.list_revisions(character_id))

    def read_revision(self, character_id: str, revision: int) -> CharacterRevision:
        """讀指定 revision 並驗證完整性；不存在／hash 不符／版本過新 → CharacterRevisionError（**不會改用其他 revision**）。"""
        p = self._rev_path(character_id, revision)
        if not p.is_file():
            hint = ""
            revs = self.list_revisions(character_id)
            if revs and revision < revs[0]:
                hint = f"（早於 history 起點 r{revs[0]}：legacy store 只保留當時狀態，更早的 revision 不存在）"
            raise CharacterRevisionError(f"{character_id}@{revision} not found{hint}")
        try:
            rev = CharacterRevision.model_validate_json(p.read_text(encoding="utf-8"))
        except ValueError as e:
            raise CharacterRevisionError(f"{character_id}@{revision}: unreadable revision file: {e}") from e
        if rev.schema_version > REVISION_SCHEMA_VERSION:
            raise CharacterRevisionError(f"{character_id}@{revision}: schema_version {rev.schema_version} newer than supported "
                                         f"{REVISION_SCHEMA_VERSION}")
        if rev.character_id != character_id or rev.revision != revision:
            raise CharacterRevisionError(f"{p.name}: content says {rev.character_id}@{rev.revision}, expected {character_id}@{revision}")
        if canonical_hash(rev.hash_payload()) != rev.content_sha256:
            raise CharacterRevisionError(f"{character_id}@{revision}: content_sha256 mismatch (revision file was modified); "
                                         "not repaired automatically")
        return rev

    def verify_revision(self, character_id: str, revision: int) -> list[str]:
        """完整性檢查（不丟例外）：回傳問題清單，空＝通過。"""
        try:
            self.read_revision(character_id, revision)
        except CharacterRevisionError as e:
            return [str(e)]
        return []

    def verify_history(self, character_id: str) -> list[str]:
        problems = [p for r in self.list_revisions(character_id) for p in self.verify_revision(character_id, r)]
        revs = self.list_revisions(character_id)
        if revs:
            head = self._head(character_id) if self._path(character_id).is_file() else None
            if head is not None and head.revision != revs[-1]:
                problems.append(f"{character_id}: head revision {head.revision} != latest history r{revs[-1]}（head 只是索引；以 history 為準）")
        return problems

    def latest_revision(self, character_id: str) -> CharacterRevision:
        revs = self.list_revisions(character_id)
        if not revs:
            raise CharacterRevisionError(f"{character_id} has no revision history yet (legacy head only)")
        return self.read_revision(character_id, revs[-1])

    # ------------------------------------------------------------ reference snapshot
    def reference_snapshot(self, definition: CharacterDefinition) -> tuple[list[ReferenceBinding], list[str], str | None]:
        """凍結當下 Reference Library metadata：Library 內綁到本角色的 asset ∪ definition.reference_asset_ids。
        找不到的 asset_id → status=missing（sha256=None，不補造）。只用主 Library（legacy identity_refs 不綁角色）。"""
        from see.core.reference_library import ReferenceLibrary, ReferenceLibraryError

        cid = definition.character_id
        found: dict[str, ReferenceBinding] = {}
        try:
            entries = ReferenceLibrary(self.workspace).list(include_legacy=False)
        except ReferenceLibraryError:
            entries = []
        for e in entries:
            a = e.asset
            if a is None or not (a.character_id == cid or a.asset_id in definition.reference_asset_ids):
                continue
            found[a.asset_id] = ReferenceBinding(
                asset_id=a.asset_id, status="inconsistent" if e.problems else "ok", role=a.role.value, category=a.category.value,
                rel_path=e.rel_path, sha256=a.sha256, is_primary=a.is_primary and a.role == RefRole.identity_face and a.character_id == cid,
                problems=list(e.problems))
        for aid in definition.reference_asset_ids:
            found.setdefault(aid, ReferenceBinding(asset_id=aid, status="missing", problems=["asset_id not found in Reference Library"]))
        bindings = [found[k] for k in sorted(found)]
        primary = next((b.asset_id for b in bindings if b.is_primary), None)
        return bindings, sorted(found), primary

    # ------------------------------------------------------------ 寫入（只新增 revision）
    def _append(self, rec: CharacterRecord, action: str, previous: int | None, **prov: Any) -> CharacterRevision:
        bindings, ids, primary = self.reference_snapshot(rec.definition)
        body = CharacterRevision.model_construct(
            schema_version=REVISION_SCHEMA_VERSION, character_id=rec.definition.character_id, revision=rec.revision,
            created_at=rec.updated_at, archived=rec.archived, definition=rec.definition, reference_asset_ids=ids,
            primary_reference_asset_id=primary, reference_bindings=bindings,
            provenance={"action": action, "previous_revision": previous, "baseline_from_legacy_current": False, **prov},
            content_sha256="0" * 64)
        payload = body.hash_payload()
        rev = CharacterRevision.model_validate({**payload, "content_sha256": canonical_hash(payload)})
        if canonical_hash(rev.hash_payload()) != rev.content_sha256:  # 防止驗證過程改寫欄位造成 hash 不一致
            raise CharacterStoreError("internal error: revision hash not stable after validation")
        d = self._history_dir(rev.character_id)
        d.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._rev_path(rev.character_id, rev.revision), "x", encoding="utf-8") as f:  # exclusive：已存在 → 拒絕覆寫
                f.write(json.dumps(rev.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True))
        except FileExistsError as e:
            raise CharacterRevisionError(f"{rev.character_id}@{rev.revision} already exists; revisions are immutable") from e
        return rev

    def _ensure_baseline(self, character_id: str) -> CharacterRecord:
        """回傳目前狀態（history 為準）；legacy（只有 head、沒有 history）→ 先把當下 head 寫成 baseline revision。"""
        if self.has_history(character_id):
            latest = self.latest_revision(character_id)  # 驗證失敗 → fail closed（不在被竄改的歷史上繼續寫）
            head = self._head(character_id) if self._path(character_id).is_file() else None
            return CharacterRecord(definition=latest.definition, archived=latest.archived, revision=latest.revision,
                                   created_at=head.created_at if head else latest.created_at, updated_at=latest.created_at)
        head = self._head(character_id)
        self._append(head, "baseline_from_legacy_current", None, baseline_from_legacy_current=True,
                     note=(f"legacy Character Store 只保留當下狀態；以 head（revision {head.revision}）作為歷史起點。"
                           f"revision 1..{head.revision - 1} 不存在，未重建、未補造。" if head.revision > 1 else
                           "legacy Character Store 只保留當下狀態；以 head 作為歷史起點（非歷史重建）。"))
        return head

    def _commit(self, before: CharacterRecord, after: CharacterRecord, action: str, **prov: Any) -> CharacterRecord:
        self._append(after, action, before.revision, **prov)
        return self._save_head(after)

    def create(self, definition: CharacterDefinition) -> CharacterRecord:
        """以指定 ID 建立（匯入／測試用；產品新角色請用 create_new()）。產生 revision 1。"""
        if self._path(definition.character_id).exists() or self.has_history(definition.character_id):
            raise CharacterStoreError(f"character_id already exists: {definition.character_id}")
        rec = CharacterRecord(definition=definition)
        self._append(rec, "create", None)
        return self._save_head(rec)

    def create_new(self, **fields: Any) -> CharacterRecord:
        """建立新角色；character_id 由系統產生（DG-29 裁示 A）。呼叫端不得指定 character_id。"""
        if "character_id" in fields:
            raise CharacterStoreError("character_id is system-generated; do not pass it")
        for _ in range(10):
            cid = new_character_id()
            if not self._path(cid).exists() and not self.has_history(cid):
                return self.create(CharacterDefinition(character_id=cid, **fields))
        raise CharacterStoreError("could not allocate a unique character_id")

    def get(self, character_id: str) -> CharacterRecord:
        """目前狀態：有 history → 以最新（已驗證）revision 為準；legacy → head。"""
        if self.has_history(character_id):
            latest = self.latest_revision(character_id)
            head = self._head(character_id) if self._path(character_id).is_file() else None
            return CharacterRecord(definition=latest.definition, archived=latest.archived, revision=latest.revision,
                                   created_at=head.created_at if head else latest.created_at, updated_at=latest.created_at)
        return self._head(character_id)

    def update(self, character_id: str, /, **changes: object) -> CharacterRecord:
        """部分更新定義欄位（character_id 不可改；rename＝改 display_name）。封存中的角色不可修改。有效修改 → 新 revision。"""
        rec = self._ensure_baseline(character_id)
        if rec.archived:
            raise CharacterStoreError(f"{character_id} is archived; restore it before editing")
        if "character_id" in changes and changes["character_id"] != character_id:
            raise CharacterStoreError("character_id is a stable identity key and cannot be changed")
        data = {**rec.definition.model_dump(), **{k: v for k, v in changes.items() if k != "character_id"}}
        definition = CharacterDefinition.model_validate(data)
        if definition == rec.definition:
            return rec
        after = rec.model_copy(update={"definition": definition, "revision": rec.revision + 1, "updated_at": _now()})
        return self._commit(rec, after, "rename" if set(changes) - {"character_id"} == {"display_name"} else "update")

    def archive(self, character_id: str) -> CharacterRecord:
        rec = self._ensure_baseline(character_id)
        if rec.archived:
            return rec
        return self._commit(rec, rec.model_copy(update={"archived": True, "revision": rec.revision + 1, "updated_at": _now()}), "archive")

    def restore(self, character_id: str) -> CharacterRecord:
        rec = self._ensure_baseline(character_id)
        if not rec.archived:
            return rec
        return self._commit(rec, rec.model_copy(update={"archived": False, "revision": rec.revision + 1, "updated_at": _now()}), "restore")

    def refresh_references(self, character_id: str) -> CharacterRecord:
        """Reference Library 綁定／換圖／primary 改變後，顯式把新狀態記成新 revision；沒變 → 不產生 revision。舊 revision 不變。"""
        rec = self._ensure_baseline(character_id)
        latest = self.latest_revision(character_id)
        bindings, _, _ = self.reference_snapshot(rec.definition)
        if [b.model_dump() for b in bindings] == [b.model_dump() for b in latest.reference_bindings]:
            return rec
        return self._commit(rec, rec.model_copy(update={"revision": rec.revision + 1, "updated_at": _now()}), "reference_refresh")

    # ------------------------------------------------------------ 其他（唯讀／備份）
    def backup(self, dest_root: Path | None = None) -> Path:
        """遷移前備份（D-064）：整份 character_library（含 history）複製到 workspace/backups/character_library-<時間>/；不改原檔。"""
        import shutil

        stamp = _now().strftime("%Y%m%dT%H%M%S%fZ")
        dest = Path(dest_root or self.root.parent / "backups") / f"character_library-{stamp}"
        if self.root.is_dir():
            shutil.copytree(self.root, dest)
        else:
            dest.mkdir(parents=True)
        return dest

    def migration_plan(self) -> dict[str, list[str]]:
        """列出 head 檔狀態（只讀）。舊檔（無 schema_version）以 v1 相容讀取，**不重寫**；`no_history`＝尚未有 baseline。"""
        plan: dict[str, list[str]] = {"current": [], "legacy_compatible": [], "newer_than_supported": [], "unreadable": [],
                                      "no_history": []}
        for p in sorted(self.root.glob("*.json")) if self.root.is_dir() else []:
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                plan["unreadable"].append(p.name)
                continue
            v = raw.get("schema_version")
            key = ("legacy_compatible" if v is None else "current" if v == CHARACTER_SCHEMA_VERSION
                   else "newer_than_supported" if isinstance(v, int) and v > CHARACTER_SCHEMA_VERSION else "unreadable")
            plan[key].append(p.name)
            if not (self.root / HISTORY_DIR / p.stem).is_dir():
                plan["no_history"].append(p.name)
        return plan

    def list(self, include_archived: bool = False) -> list[CharacterRecord]:
        if not self.root.is_dir():
            return []
        recs = [self.get(p.stem) for p in sorted(self.root.glob("*.json"))]
        return [r for r in recs if include_archived or not r.archived]
