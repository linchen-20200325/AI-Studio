"""Provider 介面。核心流程只依賴這裡的抽象，不得 import 具體供應商。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from see.models.cost import CostEstimate
from see.models.provider import ProviderInfo

T = TypeVar("T", bound=BaseModel)


class BaseProvider(ABC):
    @property
    @abstractmethod
    def info(self) -> ProviderInfo: ...

    def is_available(self) -> bool:
        """此環境是否可用（工具存在、網路可達、key 存在）。預設 True。"""
        return True

    def _estimate(self, units: float, unit_name: str, cost: float = 0.0, currency: str = "USD") -> CostEstimate:
        return CostEstimate(
            provider=self.info.name, model=self.info.model, cost_tier=self.info.cost_tier,
            units=units, unit_name=unit_name, estimated_cost=cost, currency=currency,
        )


# ---------------------------------------------------------------- LLM
class LLMRequest(BaseModel):
    task: str = Field(description="script | storyboard | ...")
    system: str = ""
    user: str = ""
    inputs: dict[str, Any] = Field(default_factory=dict, description="結構化輸入（mock 直接讀這裡）")
    params: dict[str, Any] = Field(default_factory=dict)


class LLMProvider(BaseProvider):
    @abstractmethod
    def complete_json(self, request: LLMRequest, response_model: type[T]) -> T:
        """回傳已通過 response_model 驗證的物件；驗證失敗必須 raise SchemaViolation。"""

    @abstractmethod
    def estimate_cost(self, request: LLMRequest) -> CostEstimate: ...


# ---------------------------------------------------------------- Image
class ImageRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""
    width: int = 1920
    height: int = 1080
    seed: int | None = None
    caption: str = Field(default="", description="placeholder 用：顯示在圖上的文字")
    params: dict[str, Any] = Field(default_factory=dict)


class ImageResult(BaseModel):
    path: str
    width: int
    height: int
    provider: str
    model: str
    meta: dict[str, Any] = Field(default_factory=dict,
                                 description="生成證據：實際 provider、最終 runtime plan、重試階梯、fallback 來源、影像統計")


class ImageProvider(BaseProvider):
    @abstractmethod
    def generate_image(self, request: ImageRequest, out_path: Path) -> ImageResult: ...

    @abstractmethod
    def estimate_cost(self, request: ImageRequest) -> CostEstimate: ...


# ---------------------------------------------------------------- Video
class VideoRequest(BaseModel):
    """image→clip 或 text→clip。Phase 0 以 image + camera_motion 產生片段。"""

    prompt: str = ""
    image_path: str | None = None
    duration: float = Field(gt=0)
    width: int = 1280
    height: int = 720
    fps: int = 25
    camera_motion: str = "static"
    audio_path: str | None = Field(default=None, description="要混入的旁白（provider 可忽略）")
    subtitle_path: str | None = Field(default=None, description="要燒錄的 SRT（provider 可忽略）")
    subtitle_font: str = ""
    seed: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class VideoResult(BaseModel):
    path: str
    duration: float
    provider: str
    model: str
    has_audio: bool = False
    has_subtitles: bool = False


class VideoProvider(BaseProvider):
    @abstractmethod
    def generate_clip(self, request: VideoRequest, out_path: Path) -> VideoResult: ...

    @abstractmethod
    def estimate_cost(self, request: VideoRequest) -> CostEstimate: ...


# ---------------------------------------------------------------- TTS
class TTSRequest(BaseModel):
    text: str = Field(min_length=1)
    language: str = "zh-TW"
    voice: str = "default"
    speed: float = Field(default=1.0, gt=0)
    params: dict[str, Any] = Field(default_factory=dict)


class TTSResult(BaseModel):
    path: str
    duration: float = Field(ge=0)
    provider: str
    model: str
    sample_rate: int | None = None
    meta: dict[str, Any] = Field(default_factory=dict, description="證據：generated_by / voice / device / fallback_from / rtf")


class VoiceInfo(BaseModel):
    """Provider-agnostic 的 voice 描述（Voice Selector 規格基礎；BACKLOG／D-028）。UI 不應只顯示內部 id。"""

    voice_id: str = Field(min_length=1, description="provider 內部 id（送進 TTSRequest.voice）")
    provider: str
    display_name: str = Field(min_length=1)
    language: str = "zh"
    gender: str = Field(default="unknown", description="female | male | neutral | unknown（由 provider 推斷或型錄給定）")
    tags: list[str] = Field(default_factory=list, description="聲線特徵，例如 narration、young、deep")
    accent_note: str = Field(default="", description="已知口音／限制（使用者真機聽感，非客觀排名）")
    preview_text: str = Field(default="你好，這是試聽。", description="試聽用句")


class TTSProvider(BaseProvider):
    @abstractmethod
    def synthesize(self, request: TTSRequest, out_path: Path) -> TTSResult: ...

    def list_voices(self) -> list[VoiceInfo]:
        """此 provider 目前本機可用的 voice；預設空（只有 default）。"""
        return []

    @abstractmethod
    def estimate_cost(self, request: TTSRequest) -> CostEstimate: ...


# ---------------------------------------------------------------- Audio (BGM / SFX)
class AudioRequest(BaseModel):
    kind: str = Field(description="bgm | sfx | ambience")
    description: str = ""
    duration: float = Field(gt=0)
    params: dict[str, Any] = Field(default_factory=dict)


class AudioResult(BaseModel):
    path: str | None
    duration: float = 0.0
    provider: str
    model: str
    meta: dict[str, Any] = Field(default_factory=dict,
                                 description="來源證據：source_type（procedural / cc0 / user / ...）、license、seed、variant")


class AudioProvider(BaseProvider):
    #: False = 此 provider 不產生任何音訊（null）；Audio Layer 直接停用，輸出與舊版完全相同
    generates_audio: bool = True

    @abstractmethod
    def generate_audio(self, request: AudioRequest, out_path: Path) -> AudioResult: ...

    @abstractmethod
    def estimate_cost(self, request: AudioRequest) -> CostEstimate: ...


# ---------------------------------------------------------------- LipSync
class LipSyncRequest(BaseModel):
    video_path: str = Field(description="已含 narration 的 scene clip")
    audio_path: str = Field(description="實際 narration 音檔（嘴型依此同步）")
    image_path: str | None = Field(default=None, description="原始靜態圖（image-driven 類模型可用）")
    character_id: str | None = None
    fps: int = 25
    params: dict[str, Any] = Field(default_factory=dict)


class LipSyncResult(BaseModel):
    path: str | None
    provider: str
    model: str
    applied: bool = False
    meta: dict[str, Any] = Field(default_factory=dict, description="證據：face_detected、frames、device、reason …")


class LipSyncProvider(BaseProvider):
    #: False = 不做任何事（null）；pipeline 跳過整個 lipsync stage，clip 與 fingerprint 不變
    applies: bool = True
    #: 能力宣告（未來選型比較用）：需要偵測到臉、可吃靜態圖、需要 GPU
    requires_face: bool = True
    accepts_image_input: bool = False
    requires_gpu: bool = False

    @abstractmethod
    def lipsync(self, request: LipSyncRequest, out_path: Path) -> LipSyncResult: ...

    @abstractmethod
    def estimate_cost(self, request: LipSyncRequest) -> CostEstimate: ...
