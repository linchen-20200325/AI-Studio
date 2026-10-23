from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from see.models.enums import CameraMotion, Status, Transition


class Dialogue(BaseModel):
    character_id: str
    text: str = Field(min_length=1)


class AudioCue(BaseModel):
    kind: str = Field(description="bgm | sfx | ambience")
    description: str
    start_offset: float = Field(default=0.0, ge=0)


class SceneDraft(BaseModel):
    """LLM storyboard 輸出的單景草稿（尚未有 scene_id / status）。"""

    index: int = Field(ge=0)
    duration: float = Field(gt=0, le=60, description="規劃秒數；實際以旁白長度校正")
    narration: str = Field(min_length=1)
    dialogue: list[Dialogue] = Field(default_factory=list)
    visual_description: str = Field(min_length=1)
    image_prompt: str = Field(min_length=1, description="中文／原語言 prompt（Placeholder 與中文模型用）")
    image_prompt_en: str = Field(default="", description="英文 prompt（SD/FLUX 類模型用；空則退回 image_prompt）")
    negative_prompt: str = ""
    video_prompt: str = ""
    camera_motion: CameraMotion = CameraMotion.STATIC
    transition: Transition = Transition.FADE
    audio_cues: list[AudioCue] = Field(default_factory=list)
    character_ids: list[str] = Field(default_factory=list)


class StoryboardDraft(BaseModel):
    scenes: list[SceneDraft] = Field(min_length=1)

    @field_validator("scenes")
    @classmethod
    def _indices_contiguous(cls, scenes: list[SceneDraft]) -> list[SceneDraft]:
        indices = [s.index for s in scenes]
        if indices != list(range(len(scenes))):
            raise ValueError(f"scene indices must be 0..n-1, got {indices}")
        return scenes


class Scene(SceneDraft):
    """正式 Scene：含 id、狀態與人工覆寫欄位。"""

    scene_id: str = Field(min_length=1)
    status: Status = Status.DRAFT
    subtitle_override: str | None = Field(default=None, description="人工覆寫字幕；None 則用 narration")
    voice: str = Field(default="default", description="TTS voice id（provider 自行解讀）；非 default 時優先於角色設定")
    narrator_id: str | None = Field(default=None, description="旁白角色（Project.characters 的 key）；None = 不用角色設定")
    speech_speed: float | None = Field(default=None, gt=0.5, lt=2.0, description="本景語速覆寫；None = 角色或專案語速")
    lipsync: bool = Field(default=False, description="本景是否做嘴型同步（需有效 LipSyncProvider；預設 False）")
    measured_narration_duration: float | None = Field(default=None, ge=0)

    @property
    def effective_image_prompt(self) -> str:
        return self.image_prompt_en.strip() or self.image_prompt

    @property
    def subtitle_text(self) -> str:
        return self.subtitle_override if self.subtitle_override is not None else self.narration

    @property
    def transition_in(self) -> Transition:
        return self.transition

    @classmethod
    def from_draft(cls, draft: SceneDraft, scene_id: str) -> "Scene":
        return cls(scene_id=scene_id, **draft.model_dump())
