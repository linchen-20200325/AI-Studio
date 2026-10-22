from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from see.models.enums import JobKind, JobStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RenderJob(BaseModel):
    job_id: str
    project_id: str
    kind: JobKind
    status: JobStatus = JobStatus.PENDING
    provider: str = "ffmpeg"
    model: str = "libx264"
    estimated_cost: float = Field(default=0.0, ge=0)
    actual_cost: float | None = Field(default=None, ge=0)
    currency: str = "USD"
    output_path: str | None = None
    created_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None
    error: str | None = None
    worker_id: str | None = None
