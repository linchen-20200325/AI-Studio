from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from see.models.approval import Approval
from see.models.asset import Asset
from see.models.enums import Status
from see.models.render_job import RenderJob
from see.models.scene import Scene
from see.models.script import Script


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CharacterAppearance(BaseModel):
    """角色外觀錨點（Character Consistency，D-032）。provider-agnostic：
    prompt 型 provider（SD 1.5）用 description／outfit／features 文字錨點；未來 IP-Adapter／LoRA 類 provider 可用 reference_images／lora。"""

    description_en: str = Field(default="", max_length=300, description="外觀（英文，供 image prompt）例如 'a young monk boy with a shaved head'")
    outfit_en: str = Field(default="", max_length=200, description="服裝，例如 'orange robe, straw sandals'")
    features_en: list[str] = Field(default_factory=list, max_length=10, description="固定特徵，例如 ['round face', 'big eyes']")
    reference_images: list[str] = Field(default_factory=list, max_length=8, description="參考圖路徑（使用者提供；目前 provider 不使用）")
    seed: int | None = Field(default=None, description="角色固定 seed 提示（provider 自行決定是否採用）")
    adapter: dict[str, str] = Field(default_factory=dict, description="未來 LoRA／embedding 名稱等（provider 專屬，未核准前不下載）")

    @property
    def anchor_text(self) -> str:
        parts = [self.description_en.strip()]
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
    script: Script | None = None
    scenes: list[Scene] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)
    approvals: list[Approval] = Field(default_factory=list)
    render_jobs: list[RenderJob] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def scene(self, scene_id: str) -> Scene:
        for s in self.scenes:
            if s.scene_id == scene_id:
                return s
        raise KeyError(scene_id)

    def touch(self) -> None:
        self.updated_at = _now()
