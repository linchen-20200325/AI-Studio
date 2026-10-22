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


class Project(BaseModel):
    project_id: str = Field(min_length=1)
    title: str = "untitled"
    input_text: str = Field(min_length=1)
    language: str = "zh-TW"
    status: Status = Status.DRAFT
    budget: float = Field(default=0.0, ge=0, description="預設 0：任何付費都需核准")
    currency: str = "USD"
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
