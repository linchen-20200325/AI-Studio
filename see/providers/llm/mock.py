"""MockLLMProvider：確定性規則產生劇本與分鏡。不需要網路、不需要 key。

目的不是品質，而是證明 INPUT → SCRIPT → STORYBOARD 的結構化鏈路成立。
"""

from __future__ import annotations

import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from see.core.errors import SchemaViolation
from see.core.prompting import build_image_prompt_en, default_negative_prompt
from see.core.subtitles import split_sentences
from see.models.cost import CostEstimate
from see.models.enums import CameraMotion, CostTier, ProviderKind, Transition
from see.models.provider import ProviderInfo
from see.models.scene import AudioCue, SceneDraft, StoryboardDraft
from see.models.script import Beat, Character, ScriptDraft
from see.providers.base import LLMProvider, LLMRequest

T = TypeVar("T", bound=BaseModel)

CHARS_PER_SECOND = 3.5  # 中文旁白估算語速（Phase 0 規劃用；實際以 TTS 量測校正）
_CAMERA_CYCLE = [CameraMotion.ZOOM_IN, CameraMotion.PAN_RIGHT, CameraMotion.ZOOM_OUT, CameraMotion.PAN_LEFT,
                 CameraMotion.PAN_UP, CameraMotion.STATIC]
_TRANSITION_CYCLE = [Transition.FADE, Transition.DISSOLVE, Transition.WIPE_LEFT, Transition.FADE]
_NAME_RE = re.compile(r"(小[\u4e00-\u9fff]{1,2}|老[\u4e00-\u9fff]{1,2}|[\u4e00-\u9fff]{1,2}(?:先生|小姐|爺爺|奶奶|媽媽|爸爸|老師))")


def _estimate_seconds(text: str, min_s: float, max_s: float) -> float:
    return round(min(max(len(text) / CHARS_PER_SECOND + 1.0, min_s), max_s), 2)


def _group_sentences(sentences: list[str], target_chars: int) -> list[str]:
    """把句子合併成每景約 target_chars 字的段落（只在句尾標點處合併）。"""
    groups: list[str] = []
    buf = ""
    for s in sentences:
        if buf and len(buf) + len(s) > target_chars:
            groups.append(buf)
            buf = s
        else:
            buf += s
    if buf:
        groups.append(buf)
    return groups


class MockLLMProvider(LLMProvider):
    def __init__(self, min_scene_s: float = 3.0, max_scene_s: float = 12.0,
                 target_total_min: float = 30.0, target_total_max: float = 60.0) -> None:
        self.min_scene_s = min_scene_s
        self.max_scene_s = max_scene_s
        self.target_total_min = target_total_min
        self.target_total_max = target_total_max
        self.calls = 0

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="mock-llm", kind=ProviderKind.LLM, cost_tier=CostTier.LOCAL_FREE,
                            model="rule-based", version="1")

    def estimate_cost(self, request: LLMRequest) -> CostEstimate:
        return self._estimate(units=len(request.user) + len(str(request.inputs)), unit_name="chars")

    def complete_json(self, request: LLMRequest, response_model: type[T]) -> T:
        self.calls += 1
        if request.task == "script":
            draft: BaseModel = self._script(request)
        elif request.task == "storyboard":
            draft = self._storyboard(request)
        else:
            raise SchemaViolation(f"mock-llm does not know task '{request.task}'")
        try:
            return response_model.model_validate(draft.model_dump())
        except ValidationError as e:
            raise SchemaViolation(str(e)) from e

    # ---------------------------------------------------------------- script
    def _script(self, request: LLMRequest) -> ScriptDraft:
        story = str(request.inputs.get("story", "")).strip()
        if not story:
            raise SchemaViolation("story is empty")
        # 句尾標點切句（只用 。！？；），再合併成 beats
        sentences = [s for s in re.split(r"(?<=[。！？!?；;])", re.sub(r"\s+", "", story)) if s]
        if not sentences:
            sentences = [story]
        total_chars = sum(len(s) for s in sentences)
        # 以目標總長的中點反推每景字數，並夾在單景上下限內
        target_total = (self.target_total_min + self.target_total_max) / 2
        n_scenes = max(3, min(12, round(total_chars / CHARS_PER_SECOND / (target_total / 6))))
        target_chars = max(int(self.min_scene_s * CHARS_PER_SECOND), total_chars // n_scenes + 1)
        target_chars = min(target_chars, int((self.max_scene_s - 1) * CHARS_PER_SECOND))
        groups = _group_sentences(sentences, target_chars)
        names = []
        for m in _NAME_RE.findall(story):
            if m not in names:
                names.append(m)
        characters = [Character(character_id=f"char_{i+1:02d}", name=n, description=f"故事中的角色「{n}」",
                                visual_prompt=f"{n}，插畫風格") for i, n in enumerate(names[:4])]
        beats = []
        for i, g in enumerate(groups):
            ids = [c.character_id for c in characters if c.name in g]
            beats.append(Beat(index=i, narration=g, visual_summary=g[:30], character_ids=ids))
        title = str(request.inputs.get("title") or re.split(r"[，。！？,、：:；;]", sentences[0])[0][:16])
        return ScriptDraft(title=title or "untitled", logline=sentences[0][:60], language="zh-TW",
                           characters=characters, beats=beats)

    # ---------------------------------------------------------------- storyboard
    def _storyboard(self, request: LLMRequest) -> StoryboardDraft:
        script = ScriptDraft.model_validate(request.inputs.get("script"))
        scenes: list[SceneDraft] = []
        for beat in script.beats:
            i = beat.index
            first = split_sentences(beat.narration)[0] if beat.narration else beat.narration
            visual = beat.visual_summary or first
            scenes.append(SceneDraft(
                index=i,
                duration=_estimate_seconds(beat.narration, self.min_scene_s, self.max_scene_s),
                narration=beat.narration,
                visual_description=f"{visual}（場景 {i+1}）",
                image_prompt=f"插畫風格，{visual}，柔和光線，電影感構圖",
                image_prompt_en=build_image_prompt_en(visual),
                negative_prompt=default_negative_prompt(),
                video_prompt=f"{visual}，緩慢鏡頭運動",
                camera_motion=_CAMERA_CYCLE[i % len(_CAMERA_CYCLE)],
                transition=Transition.FADE if i == 0 else _TRANSITION_CYCLE[i % len(_TRANSITION_CYCLE)],
                audio_cues=[AudioCue(kind="bgm", description="輕柔背景音樂")] if i == 0 else [],
                character_ids=beat.character_ids,
            ))
        return StoryboardDraft(scenes=scenes)
