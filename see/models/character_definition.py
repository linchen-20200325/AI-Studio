"""Character Definition／Reference Asset schema 與 Character Validation Gate（D-058；PROJECT_RULES §17；ARCHITECTURE §17）。

原則：
- `character_id` 是**穩定身份鍵**，不代表性別、位置、style、mood、voice 或角色類型；這些全部是顯式欄位。
- `gender_presentation` 是使用者指定的「畫面上的性別呈現」，不是生理性別；未指定＝`unspecified`，程式不補值。
- 不從 reference image 推論任何敏感身份、國籍或族群；`appearance_region` 只有使用者明確指定時才填。
- Identity（角色是誰、長什麼樣）與 Style／Mood／Voice 分離：角色只持有「預設」引用，Scene 可 override。
- Reference asset 的歸屬與用途由 metadata 決定，**不靠檔名或資料夾猜**。
- 現有 `CharacterAppearance`／`CharacterTraits`（prompt 錨點層，D-048）保留；本 schema 經 `to_appearance()` 產生它們。
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from see.models.project import CharacterAppearance, CharacterTraits

ID_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"  # 產品建議 char_001、char_002…；A／B 只作測試槽位或 UI 暫時排序


class CharacterType(str, Enum):
    person = "person"
    animal = "animal"
    fictional_character = "fictional_character"


class GenderPresentation(str, Enum):
    """畫面上的性別呈現（≠ biological sex）。unspecified＝使用者未指定，prompt 不輸出任何性別詞。"""

    male = "male"
    female = "female"
    nonbinary = "nonbinary"
    unspecified = "unspecified"


# prompt 型 provider 的英文錨點詞；unspecified 不輸出（不補值）
GENDER_PROMPT_WORD = {GenderPresentation.male: "man", GenderPresentation.female: "woman",
                      GenderPresentation.nonbinary: "person", GenderPresentation.unspecified: ""}


class RefCategory(str, Enum):
    people = "people"
    animals = "animals"
    characters = "characters"
    backgrounds = "backgrounds"
    styles = "styles"


class RefRole(str, Enum):
    identity_face = "identity_face"
    full_body = "full_body"
    outfit = "outfit"
    pose = "pose"
    style_reference = "style_reference"
    background_reference = "background_reference"


class SourceType(str, Enum):
    user_supplied = "user_supplied"
    generated = "generated"
    imported = "imported"


class CommercialClearance(str, Enum):
    cleared = "cleared"
    not_cleared = "not_cleared"
    unknown = "unknown"


# 目前程式實際支援的 (category, role)；其他組合＝not yet supported（資料夾存在不代表功能完成）
SUPPORTED_CONDITIONING = {(RefCategory.people, RefRole.identity_face): "S4 --identity（IP-Adapter plus-face；研究用，D-054／D-057）"}
CHARACTER_ROLES = {RefRole.identity_face, RefRole.full_body, RefRole.outfit, RefRole.pose}
ROLE_CATEGORIES = {RefRole.identity_face: {RefCategory.people, RefCategory.animals, RefCategory.characters},
                   RefRole.full_body: {RefCategory.people, RefCategory.animals, RefCategory.characters},
                   RefRole.outfit: {RefCategory.people, RefCategory.characters},
                   RefRole.pose: {RefCategory.people, RefCategory.animals, RefCategory.characters},
                   RefRole.style_reference: {RefCategory.styles},
                   RefRole.background_reference: {RefCategory.backgrounds}}
CATEGORY_FOR_TYPE = {CharacterType.person: RefCategory.people, CharacterType.animal: RefCategory.animals,
                     CharacterType.fictional_character: RefCategory.characters}


def support_status(category: RefCategory, role: RefRole) -> str:
    return SUPPORTED_CONDITIONING.get((category, role), "not yet supported")


class ReferenceAsset(BaseModel):
    """一張 reference 的 metadata（圖片本身只在本機 Reference Library，不進 Git；GitHub 只存 schema／規則）。"""

    asset_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,80}$")
    category: RefCategory
    file_path: str = Field(min_length=1, description="本機路徑（不收 URL）")
    character_id: str | None = Field(default=None, description="綁定角色；style／background reference 可為 None")
    role: RefRole
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_type: SourceType
    provenance: dict[str, str | int | None] = Field(default_factory=dict, description="例 source_evidence、consent、imported_from")
    commercial_clearance_status: CommercialClearance = CommercialClearance.unknown
    is_primary: bool = False
    notes: str = Field(default="", max_length=500)

    @field_validator("file_path")
    @classmethod
    def _local_only(cls, v: str) -> str:
        if "://" in v:
            raise ValueError("reference assets must be local files (Local First, PROJECT_RULES §16)")
        return v


class VoiceAssignment(BaseModel):
    """角色的「預設」聲音（與身份資料分離，經 character_id 綁定；Scene 可 override voice／speed／emotion）。"""

    voice_id: str = Field(default="default", min_length=1)
    speed: float | None = Field(default=None, gt=0.5, lt=2.0)
    emotion: str = Field(default="", max_length=40)


class CharacterDefinition(BaseModel):
    """產品用角色定義（身份＋外觀＋預設引用）。所有可選欄位預設為空／unspecified：缺資料不補值。"""

    character_id: str = Field(pattern=ID_PATTERN)
    display_name: str = Field(min_length=1, max_length=64)
    character_type: CharacterType = CharacterType.person
    gender_presentation: GenderPresentation = GenderPresentation.unspecified
    age_impression: str = Field(default="", max_length=60, description="例 'in her 20s'、'middle-aged'")
    appearance_region: str = Field(default="", max_length=60, description="只有使用者明確指定時才填；空＝unspecified")
    face_shape: str = Field(default="", max_length=60)
    facial_features: list[str] = Field(default_factory=list, max_length=8)
    hair_style: str = Field(default="", max_length=60)
    hair_color: str = Field(default="", max_length=40)
    distinctive_marks: list[str] = Field(default_factory=list, max_length=8)
    outfit: str = Field(default="", max_length=200)
    expression: str = Field(default="", max_length=60)
    reference_asset_ids: list[str] = Field(default_factory=list, max_length=16)
    default_style_profile: str | None = None
    default_mood_profile: str | None = None
    voice_profile: VoiceAssignment | None = None
    notes: str = Field(default="", max_length=500)

    def to_appearance(self) -> CharacterAppearance:
        """橋接到既有 prompt 錨點層（D-048）。style／mood／voice 不進外觀錨點（解耦）。"""
        features = ([f"{self.face_shape.strip()} face"] if self.face_shape.strip() else []) + list(self.facial_features)
        if self.expression.strip():
            features.append(f"{self.expression.strip()} expression")
        traits = CharacterTraits(gender_presentation=GENDER_PROMPT_WORD[self.gender_presentation],
                                 age_range=self.age_impression, appearance_region=self.appearance_region,
                                 hair_style=self.hair_style, hair_color=self.hair_color, facial_features=features,
                                 distinctive_marks=list(self.distinctive_marks))
        return CharacterAppearance(outfit_en=self.outfit, traits=traits)


class Horizontal(str, Enum):
    left = "left"
    center = "center"
    right = "right"


class Depth(str, Enum):
    foreground = "foreground"
    midground = "midground"
    background = "background"


class ScenePlacement(BaseModel):
    """角色在某個 Scene 的擺位（與身份分離；character_id 不隱含位置）。"""

    character_id: str = Field(pattern=ID_PATTERN)
    horizontal: Horizontal
    depth: Depth = Depth.midground
    shot_size: str = Field(default="", max_length=40, description="例 close-up、medium shot")
    action: str = Field(default="", max_length=80)
    pose: str = Field(default="", max_length=80)


class GateIssue(BaseModel):
    code: str
    message: str
    blocking: bool = True


def validate_characters(characters: list[CharacterDefinition], assets: list[ReferenceAsset],
                        placements: list[ScenePlacement], *, repo_root: Path | None = None,
                        require_identity_reference: bool = False, final_output: bool = False) -> list[GateIssue]:
    """Character Validation Gate：生成前檢查 metadata 是否一致。任何 blocking issue → 呼叫端必須 fail closed（不生成）。"""
    issues: list[GateIssue] = []
    ids = [c.character_id for c in characters]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        issues.append(GateIssue(code="duplicate_character_id", message=f"character_id 重複：{dup}"))
    known = set(ids)
    asset_ids = [a.asset_id for a in assets]
    for dup in sorted({i for i in asset_ids if asset_ids.count(i) > 1}):
        issues.append(GateIssue(code="duplicate_asset_id", message=f"asset_id 重複：{dup}"))
    by_sha: dict[str, set[str]] = {}
    for a in assets:
        if a.role in CHARACTER_ROLES:
            if a.character_id is None:
                issues.append(GateIssue(code="asset_unbound", message=f"{a.asset_id}：角色用途（{a.role.value}）必須綁定 character_id"))
            elif a.character_id not in known:
                issues.append(GateIssue(code="asset_unknown_character", message=f"{a.asset_id} 綁到不存在的角色 {a.character_id}"))
            else:
                by_sha.setdefault(a.sha256, set()).add(a.character_id)
        if a.category not in ROLE_CATEGORIES[a.role]:
            issues.append(GateIssue(code="role_category_mismatch",
                                    message=f"{a.asset_id}：用途 {a.role.value} 不屬於類別 {a.category.value}"))
        if repo_root is not None:
            p = Path(a.file_path).resolve()
            root = repo_root.resolve()
            if p.is_relative_to(root) and not p.is_relative_to(root / "workspace"):
                issues.append(GateIssue(code="private_image_in_repo",
                                        message=f"{a.asset_id}：圖片位於 repo 內且不在 workspace/（可能被 commit）：{a.file_path}"))
        if a.commercial_clearance_status != CommercialClearance.cleared:
            issues.append(GateIssue(code="commercial_clearance_unknown" if a.commercial_clearance_status == CommercialClearance.unknown
                                    else "commercial_not_cleared",
                                    message=f"{a.asset_id}：commercial_clearance={a.commercial_clearance_status.value}",
                                    blocking=final_output))
    for sha, owners in by_sha.items():
        if len(owners) > 1:
            issues.append(GateIssue(code="reference_shared_across_characters",
                                    message=f"同一張 reference（sha256 {sha[:12]}…）綁到多個角色：{sorted(owners)}"))
    by_char_ref = {cid: [a for a in assets if a.character_id == cid] for cid in known}
    for c in characters:
        for aid in c.reference_asset_ids:
            a = next((x for x in assets if x.asset_id == aid), None)
            if a is None:
                issues.append(GateIssue(code="missing_asset", message=f"{c.character_id} 引用不存在的 asset {aid}"))
            elif a.character_id != c.character_id:
                issues.append(GateIssue(code="asset_owner_mismatch",
                                        message=f"{c.character_id} 引用的 {aid} 實際綁定 {a.character_id}"))
        for a in by_char_ref[c.character_id]:
            if a.role in CHARACTER_ROLES and a.category != CATEGORY_FOR_TYPE[c.character_type]:
                issues.append(GateIssue(code="asset_type_mismatch",
                                        message=f"{a.asset_id}：{c.character_type.value} 角色不應使用 {a.category.value} 類 reference"))
        if require_identity_reference and not any(a.role == RefRole.identity_face for a in by_char_ref[c.character_id]):
            issues.append(GateIssue(code="missing_identity_reference", message=f"{c.character_id} 沒有 identity_face reference"))
        primaries = [a for a in by_char_ref[c.character_id] if a.is_primary and a.role == RefRole.identity_face]
        if len(primaries) > 1:
            issues.append(GateIssue(code="multiple_primary_references", message=f"{c.character_id} 有多張主要 identity reference"))
    placed = [p.character_id for p in placements]
    for p in placements:
        if p.character_id not in known:
            issues.append(GateIssue(code="placement_unknown_character", message=f"placement 指向不存在的角色 {p.character_id}"))
    for cid in ids:
        if placed.count(cid) != 1:
            issues.append(GateIssue(code="placement_missing" if placed.count(cid) == 0 else "placement_duplicate",
                                    message=f"{cid} 需要恰好一個明確 placement（目前 {placed.count(cid)} 個）"))
    spots = [(p.horizontal, p.depth) for p in placements]
    if len(placements) > 1 and len(set(spots)) != len(spots):
        issues.append(GateIssue(code="placement_collision", message="兩個角色的 horizontal＋depth 相同，位置不明確"))
    return issues


def blocking(issues: list[GateIssue]) -> list[GateIssue]:
    return [i for i in issues if i.blocking]


# ---------------------------------------------------------------- Character Confirmation payload（D-058 §17.6；D-062）
class ConfirmationRow(BaseModel):
    character_id: str
    display_name: str
    character_type: CharacterType
    gender_presentation: GenderPresentation
    primary_reference: dict[str, str] | None  # {asset_id, file_name, sha256}；None＝沒有主要 identity reference
    outfit: str
    style: str | None
    mood: str | None
    voice: str | None
    placement: dict[str, str] | None


class ConfirmationPayload(BaseModel):
    rows: list[ConfirmationRow]
    issues: list[GateIssue]
    can_generate: bool  # 有 blocking issue → False（UI 不得允許按「生成」）


def confirmation_payload(characters: list[CharacterDefinition], assets: list[ReferenceAsset], placements: list[ScenePlacement],
                         *, scene_style: str | None = None, scene_mood: str | None = None,
                         scene_voice: dict[str, str] | None = None, **gate_kw) -> ConfirmationPayload:
    """生成前人工確認卡的資料（UI 外觀未定）。style／mood：Scene override 優先，否則角色預設；voice：scene_voice[character_id]
    優先，否則角色 voice_profile。缺值保持 None（不補值）。同時執行 Character Validation Gate。"""
    issues = validate_characters(characters, assets, placements, **gate_kw)
    by_place = {p.character_id: p for p in placements}
    rows = []
    for c in characters:
        prim = [a for a in assets if a.character_id == c.character_id and a.role == RefRole.identity_face and a.is_primary]
        ref = prim[0] if len(prim) == 1 else None
        p = by_place.get(c.character_id)
        voice = (scene_voice or {}).get(c.character_id) or (c.voice_profile.voice_id if c.voice_profile else None)
        rows.append(ConfirmationRow(
            character_id=c.character_id, display_name=c.display_name, character_type=c.character_type,
            gender_presentation=c.gender_presentation,
            primary_reference={"asset_id": ref.asset_id, "file_name": Path(ref.file_path).name, "sha256": ref.sha256} if ref else None,
            outfit=c.outfit, style=scene_style or c.default_style_profile, mood=scene_mood or c.default_mood_profile, voice=voice,
            placement={"horizontal": p.horizontal.value, "depth": p.depth.value, "shot_size": p.shot_size} if p else None))
    return ConfirmationPayload(rows=rows, issues=issues, can_generate=not blocking(issues))
