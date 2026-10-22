from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from see.models.enums import Transition


class TimelineItem(BaseModel):
    scene_id: str
    index: int = Field(ge=0)
    clip_path: str
    clip_duration: float = Field(gt=0)
    start: float = Field(ge=0, description="在最終影片中的起始秒數（含轉場重疊）")
    end: float = Field(gt=0)
    transition_in: Transition = Transition.FADE
    transition_in_duration: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _check_range(self) -> "TimelineItem":
        if self.end <= self.start:
            raise ValueError("end must be > start")
        return self


class Timeline(BaseModel):
    fps: int = Field(default=25, gt=0)
    width: int = Field(default=1280, gt=0)
    height: int = Field(default=720, gt=0)
    items: list[TimelineItem] = Field(min_length=1)

    @property
    def total_duration(self) -> float:
        return self.items[-1].end
