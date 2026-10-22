"""Worker / Executor 抽象層（PROJECT_RULES §3）。

Phase 0 只有 LocalExecutor；未來 QueueExecutor（NAS 排隊 / GPU PC 領取）實作同一介面。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from see.models.worker import TaskSpec, WorkerInfo


@dataclass
class Task:
    task_id: str
    kind: str
    fn: Callable[..., Any]
    kwargs: dict[str, Any] = field(default_factory=dict)
    requires: set[str] = field(default_factory=lambda: {"cpu"})

    def spec(self) -> TaskSpec:
        return TaskSpec(task_id=self.task_id, kind=self.kind, requires=set(self.requires),
                        payload={k: v for k, v in self.kwargs.items() if isinstance(v, (str, int, float, bool))})


@dataclass
class TaskResult:
    task_id: str
    ok: bool
    value: Any = None
    error: str | None = None
    worker_id: str = ""


class Executor(ABC):
    @abstractmethod
    def submit(self, task: Task) -> TaskResult: ...

    @abstractmethod
    def worker_info(self) -> WorkerInfo: ...

    def run(self, task: Task) -> Any:
        """同步取值；失敗則 raise 原始例外訊息。"""
        result = self.submit(task)
        if not result.ok:
            raise RuntimeError(f"task {task.task_id} ({task.kind}) failed on {result.worker_id}: {result.error}")
        return result.value
