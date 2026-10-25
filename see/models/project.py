from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator

from see.models.approval import Approval
from see.models.asset import Asset
from see.models.character_binding import CAST_SCHEMA_VERSION, CharacterBinding
from see.models.enums import Status
from see.models.preferences import PreferenceSet
from see.models.render_job import RenderJob
from see.models.scene import Scene
from see.models.script import Script


def _now() -> datetime:
    return datetime.now(timezone.utc)


_TXT = {"default": "", "max_length": 80}


def _clean(xs: list[str]) -> list[str]:
    return [x.strip() for x in xs if x and x.strip()]


class CharacterTraits(BaseModel):
    """結構化人物設定（D-046／D-047；PROJECT_RULES §16）。全部可選、自由文字（英文，供 prompt 型 provider）：
    **不提供任何性別／族群／年齡預設值，也不做 enum**——由使用者描述，空欄位就不輸出。
    `appearance_region` 只是可描述外觀（例 'East Asian'），不對應任何固定臉型；五官由 `facial_features` 另外描述、隨時可改。
    model-agnostic：換 image model 時原樣沿用；model-specific 參數放 `CharacterAppearance.adapter`／模型 preset。"""

    gender_presentation: str = Field(**_TXT, description="例 'woman'、'man'、'person'")
    age: int | None = Field(default=None, ge=1, le=120)
    age_range: str = Field(**_TXT, description="例 'in her 20s'、'middle-aged'；與 age 擇一即可")
    appearance_region: str = Field(**_TXT, description="地區外貌描述，例 'East Asian'、'Western European'")
    hair_style: str = Field(**_TXT, description="例 'short bob'、'long ponytail'")
    hair_color: str = Field(**_TXT, description="例 'black'、'chestnut brown'")
    facial_features: list[str] = Field(default_factory=list, max_length=8, description="例 ['almond-shaped eyes', 'thin eyebrows']")
    body_type: str = Field(**_TXT, description="例 'slim'、'athletic build'")
    distinctive_marks: list[str] = Field(default_factory=list, max_length=8, description="辨識特徵，例 ['mole under left eye', 'round glasses']")

    @property
    def is_empty(self) -> bool:
        return not self.anchor_parts

    @property
    def anchor_parts(self) -> list[str]:
        """確定性組裝順序：主體（年齡＋地區＋性別呈現）→ 年齡區間 → 體型 → 髮 → 五官 → 辨識特徵。"""
        subject = " ".join(x for x in (f"{self.age}-year-old" if self.age else "", self.appearance_region.strip(),
                                        self.gender_presentation.strip()) if x)
        hair = " ".join(x for x in (self.hair_style.strip(), f"{self.hair_color.strip()} hair" if self.hair_color.strip() else "") if x)
        if self.hair_style.strip() and not self.hair_color.strip() and "hair" not in self.hair_style.lower():
            hair += " hair"
        body = self.body_type.strip()
        return [x for x in (subject, self.age_range.strip() if not self.age else "", body, hair) if x] + \
            _clean(self.facial_features) + _clean(self.distinctive_marks)


class CharacterAppearance(BaseModel):
    """角色外觀錨點（Character Consistency，D-032）。provider-agnostic：
    prompt 型 provider（SD 1.5）用 description／outfit／features 文字錨點；未來 IP-Adapter／LoRA 類 provider 可用 reference_images／lora。"""

    description_en: str = Field(default="", max_length=300, description="外觀（英文，供 image prompt）例如 'a young monk boy with a shaved head'")
    outfit_en: str = Field(default="", max_length=200, description="服裝，例如 'orange robe, straw sandals'")
    features_en: list[str] = Field(default_factory=list, max_length=10, description="固定特徵，例如 ['round face', 'big eyes']")
    reference_images: list[str] = Field(default_factory=list, max_length=8, description="參考圖路徑（使用者提供；目前 provider 不使用）")
    seed: int | None = Field(default=None, description="角色固定 seed 提示（provider 自行決定是否採用）")
    adapter: dict[str, str] = Field(default_factory=dict, description="未來 LoRA／embedding 名稱等（provider 專屬，未核准前不下載）")
    traits: CharacterTraits | None = Field(default=None, description="結構化人物設定（D-047）；None＝只用舊欄位（fingerprint 不變）")

    @field_validator("reference_images")
    @classmethod
    def _local_only(cls, v: list[str]) -> list[str]:
        # PROJECT_RULES §16：真人參考照是敏感素材 → 只接受本機路徑（Local First；不收 URL，避免暗中交給第三方）
        bad = [x for x in v if "://" in x]
        if bad:
            raise ValueError(f"reference_images must be local file paths (Local First, PROJECT_RULES §16): {bad}")
        return v

    @property
    def anchor_text(self) -> str:
        parts = list(self.traits.anchor_parts) if self.traits is not None else []
        parts.append(self.description_en.strip())
        if self.outfit_en.strip():
            parts.append(f"wearing {self.outfit_en.strip()}")
        parts += [f.strip() for f in self.features_en if f.strip()]
        return ", ".join(p for p in parts if p)


class CharacterVoice(BaseModel):
    """角色 → voice／語速設定（Voice Selection 規格，D-028）。provider-agnostic：voice_id 由當時的 TTS provider 解讀。

    流程：設定 voice／語速 → 試聽 → `confirmed=True` → 才可 Final render（D-030）。任何修改都會清掉 confirmed。
    """

    character_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    display_name: str = Field(default="", max_length=64)
    voice_id: str = Field(default="default", min_length=1, description="送進 TTSRequest.voice；default = provider 預設")
    provider: str = Field(default="", description="設定時的 TTS provider 名稱（資訊用，不綁死）")
    speed: float | None = Field(default=None, gt=0.5, lt=2.0, description="None = 沿用 project.speech_speed")
    confirmed: bool = False
    confirmed_at: datetime | None = None
    appearance: CharacterAppearance | None = Field(default=None, description="外觀錨點；None = 不做一致性處理")


# 角色設定（voice + appearance）。保留 CharacterVoice 名稱以相容既有 project.json／程式。
CharacterProfile = CharacterVoice


class OutputSpec(BaseModel):
    """每個 Project 的輸出規格（UI 可選比例）。"""

    width: int = Field(default=1280, gt=0)
    height: int = Field(default=720, gt=0)
    fps: int = Field(default=25, gt=0)

    @classmethod
    def from_aspect(cls, aspect: str, fps: int = 25) -> "OutputSpec":
        table = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (1080, 1080)}
        if aspect not in table:
            raise ValueError(f"unsupported aspect '{aspect}'; choose one of {sorted(table)}")
        w, h = table[aspect]
        return cls(width=w, height=h, fps=fps)

    @property
    def aspect(self) -> str:
        for k, (w, h) in {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (1080, 1080)}.items():
            if (w, h) == (self.width, self.height):
                return k
        return f"{self.width}x{self.height}"


class Project(BaseModel):
    project_id: str = Field(min_length=1)
    title: str = "untitled"
    input_text: str = Field(min_length=1)
    language: str = "zh-TW"
    status: Status = Status.DRAFT
    budget: float = Field(default=0.0, ge=0, description="預設 0：任何付費都需核准")
    currency: str = "TWD"
    output: OutputSpec = Field(default_factory=OutputSpec)
    speech_speed: float = Field(default=1.0, gt=0.5, lt=2.0, description="TTS 語速倍率")
    characters: dict[str, CharacterVoice] = Field(default_factory=dict, description="角色設定：voice（D-030）＋ appearance（D-032）")
    style_id: str = Field(default="default", description="Style Profile id（see/core/styles.py；default = Phase 1 既有風格）")
    preferences: PreferenceSet | None = Field(default=None, description="D-062 Project default 偏好（Mood／Lighting／Color／Camera／Composition／Generation）；None＝無")
    # D-068 Batch 3：Character Library 綁定（character_id＋pinned revision）。**foundation only**：
    # D-073 Batch 6A：有 committed migration 且 cast 一致的專案，production 角色來源＝pinned cast（see/core/character_source.py）；否則 legacy Project.characters。
    cast: list[CharacterBinding] = Field(default_factory=list, description="D-068 pinned Library 角色（foundation；尚未接 pipeline）")
    cast_schema_version: int | None = Field(default=None, description="cast 格式版本；None＝沒有 cast（舊專案）")
    script: Script | None = None
    scenes: list[Scene] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)
    approvals: list[Approval] = Field(default_factory=list)
    render_jobs: list[RenderJob] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def _validate_cast(self) -> "Project":
        if self.cast_schema_version is not None and self.cast_schema_version > CAST_SCHEMA_VERSION:
            raise ValueError(f"cast_schema_version {self.cast_schema_version} is newer than supported {CAST_SCHEMA_VERSION}; "
                             "update the program instead of editing this project")  # fail safe：不猜新格式
        ids = [b.character_id for b in self.cast]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            raise ValueError(f"duplicate character_id in Project.cast: {dup}")
        if self.cast and self.cast_schema_version is None:
            self.cast_schema_version = CAST_SCHEMA_VERSION
        return self

    def scene(self, scene_id: str) -> Scene:
        for s in self.scenes:
            if s.scene_id == scene_id:
                return s
        raise KeyError(scene_id)

    def touch(self) -> None:
        self.updated_at = _now()
