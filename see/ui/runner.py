"""BackgroundRunner：Web UI 與 pipeline 之間的最小工作排程（單機、單 worker）。

Compute Agnostic：UI 只透過 submit()/status() 操作；未來 NAS queue + GPU worker 以同介面替換。
"""

from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class JobState:
    project_id: str
    state: str = "idle"  # idle | queued | running | done | failed
    stage: str = ""
    message: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"project_id": self.project_id, "state": self.state, "stage": self.stage, "message": self.message,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "finished_at": self.finished_at.isoformat() if self.finished_at else None, "error": self.error}


@dataclass
class BackgroundRunner:
    sync: bool = False  # True：同步執行（測試用）
    _states: dict[str, JobState] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _pool: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(max_workers=1, thread_name_prefix="see-job"))

    def status(self, project_id: str) -> JobState:
        with self._lock:
            return self._states.get(project_id) or JobState(project_id=project_id)

    def is_busy(self, project_id: str) -> bool:
        return self.status(project_id).state in ("queued", "running")

    def set_stage(self, project_id: str, stage: str, message: str = "") -> None:
        with self._lock:
            st = self._states.setdefault(project_id, JobState(project_id=project_id))
            st.stage, st.message = stage, message

    def submit(self, project_id: str, stage: str, fn: Callable[[], Any]) -> JobState:
        with self._lock:
            st = self._states.get(project_id)
            if st and st.state in ("queued", "running"):
                raise RuntimeError(f"project {project_id} already has a running job ({st.stage})")
            st = JobState(project_id=project_id, state="queued", stage=stage)
            self._states[project_id] = st

        def _run() -> None:
            with self._lock:
                st.state, st.started_at = "running", datetime.now(timezone.utc)
            try:
                fn()
                with self._lock:
                    st.state, st.message = "done", "完成"
            except Exception as e:  # noqa: BLE001 — 任何失敗都要回報到 UI
                with self._lock:
                    st.state, st.error = "failed", f"{type(e).__name__}: {e}"
                    st.message = traceback.format_exc()[-2000:]
            finally:
                with self._lock:
                    st.finished_at = datetime.now(timezone.utc)

        if self.sync:
            _run()
        else:
            self._pool.submit(_run)
        return st
