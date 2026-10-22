from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkerInfo(BaseModel):
    worker_id: str
    capabilities: set[str] = Field(default_factory=set, description="例如 cpu, ffmpeg, gpu, network")
    location: str = Field(default="local", description="local | nas | gpu-pc | cloud")


class TaskSpec(BaseModel):
    """Task 的可序列化描述（未來進 queue 用）。執行函式本身在 see.workers.base.Task。"""

    task_id: str
    kind: str
    requires: set[str] = Field(default_factory=set)
    payload: dict[str, Any] = Field(default_factory=dict)
