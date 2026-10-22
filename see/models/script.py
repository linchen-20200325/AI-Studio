from __future__ import annotations

from pydantic import BaseModel, Field


class Character(BaseModel):
    character_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    visual_prompt: str = ""


class Beat(BaseModel):
    """劇本的一個節拍：一段旁白 + 視覺摘要。Storyboard 階段會展開成 Scene。"""

    index: int = Field(ge=0)
    narration: str = Field(min_length=1)
    visual_summary: str = ""
    character_ids: list[str] = Field(default_factory=list)


class Script(BaseModel):
    title: str = Field(min_length=1)
    logline: str = ""
    language: str = "zh-TW"
    characters: list[Character] = Field(default_factory=list)
    beats: list[Beat] = Field(min_length=1)


class ScriptDraft(Script):
    """LLM 回應的 schema（與 Script 相同，獨立命名以便未來擴充）。"""
