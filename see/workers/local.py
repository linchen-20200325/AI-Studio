from __future__ import annotations

import shutil

from see.core.errors import SeeError
from see.models.worker import WorkerInfo
from see.workers.base import Executor, Task, TaskResult


class LocalExecutor(Executor):
    """同步在本機執行。能力由環境偵測。"""

    def __init__(self, worker_id: str = "local") -> None:
        caps = {"cpu"}
        if shutil.which("ffmpeg") and shutil.which("ffprobe"):
            caps.add("ffmpeg")
        if shutil.which("espeak-ng"):
            caps.add("espeak")
        self._info = WorkerInfo(worker_id=worker_id, capabilities=caps, location="local")
        self.executed: list[str] = []

    def worker_info(self) -> WorkerInfo:
        return self._info

    def submit(self, task: Task) -> TaskResult:
        missing = task.requires - self._info.capabilities
        if missing:
            return TaskResult(task_id=task.task_id, ok=False, worker_id=self._info.worker_id,
                              error=f"worker lacks capabilities {sorted(missing)}")
        self.executed.append(task.task_id)
        try:
            return TaskResult(task_id=task.task_id, ok=True, value=task.fn(**task.kwargs), worker_id=self._info.worker_id)
        except SeeError as e:
            return TaskResult(task_id=task.task_id, ok=False, error=f"{type(e).__name__}: {e}", worker_id=self._info.worker_id)
