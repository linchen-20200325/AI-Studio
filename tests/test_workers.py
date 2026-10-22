from see.core.errors import RenderError
from see.workers.base import Task
from see.workers.local import LocalExecutor


def test_local_executor_runs_task_and_records():
    ex = LocalExecutor()
    assert ex.run(Task(task_id="t1", kind="add", fn=lambda a, b: a + b, kwargs={"a": 1, "b": 2})) == 3
    assert ex.executed == ["t1"]


def test_local_executor_rejects_missing_capability():
    ex = LocalExecutor()
    res = ex.submit(Task(task_id="t2", kind="gpu-job", fn=lambda: 1, requires={"gpu"}))
    assert not res.ok and "gpu" in (res.error or "")


def test_local_executor_wraps_see_errors():
    def boom():
        raise RenderError("ffmpeg died")
    res = LocalExecutor().submit(Task(task_id="t3", kind="x", fn=boom))
    assert not res.ok and "RenderError" in (res.error or "")
