from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from see.models.enums import CameraMotion, Status, Transition
from see.models.preferences import PreferenceSet
from see.models.scene_character import SceneCharacter


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
    preferences: PreferenceSet | None = Field(default=None, description="D-062 Scene override（逐欄位覆寫 Project default）；None＝不覆寫")
    image_prompt_zh: str = Field(default="", max_length=2000,
                                 description="D-063 一般使用者的中文圖片描述（UI「圖片描述」）；非空時由 prompt builder 轉成模型英文 prompt")
    characters: list[SceneCharacter] = Field(default_factory=list, max_length=10,
                                             description="D-063 本幕人物演出覆寫（表情／動作／姿勢／服裝…）；不改角色永久設定")

    @model_validator(mode="after")
    def _characters_in_scene(self) -> "Scene":
        ids = [c.character_id for c in self.characters]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate scene character override: {ids}")
        stray = sorted(set(ids) - set(self.character_ids))
        if stray:  # fail closed：覆寫只能指向本幕出場角色
            raise ValueError(f"scene character overrides {stray} are not in scene.character_ids {self.character_ids}")
        known = set(self.character_ids)
        bad = sorted({c.gaze.target_character_id for c in self.characters if c.gaze and c.gaze.target_character_id} - known)
        if bad:
            raise ValueError(f"gaze target {bad} is not in scene.character_ids")
        return self

    @property
    def effective_image_prompt(self) -> str:
        """legacy 來源（無中文圖片描述時）：image_prompt_en，空則 image_prompt。中文來源由 see.core.scene_prompt 處理。"""
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
