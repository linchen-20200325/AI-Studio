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
