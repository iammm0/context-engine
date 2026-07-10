import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from models.task import TaskDispatchInfo
from services import task_status


class FakeAsyncResult:
    def __init__(self, state, ready, successful=False, result=None, info=None):
        self.state = state
        self._ready = ready
        self._successful = successful
        self.result = result
        self.info = info

    def ready(self):
        return self._ready

    def successful(self):
        return self._successful


def test_enrich_task_dispatch_keeps_local_backend_unchanged(monkeypatch):
    task = {"backend": "fastapi-background", "task_id": None}

    enriched = task_status.enrich_task_dispatch(task)

    assert enriched == task


def test_enrich_task_dispatch_adds_success_state(monkeypatch):
    monkeypatch.setattr(
        task_status,
        "_get_celery_result",
        lambda task_id: FakeAsyncResult("SUCCESS", True, True, {"document_id": "doc1"}),
    )

    enriched = task_status.enrich_task_dispatch({"backend": "celery", "task_id": "task-1"})

    assert enriched == {
        "backend": "celery",
        "task_id": "task-1",
        "state": "SUCCESS",
        "ready": True,
        "successful": True,
        "result": {"document_id": "doc1"},
    }


def test_enrich_task_dispatch_exposes_running_task_meta(monkeypatch):
    monkeypatch.setattr(
        task_status,
        "_get_celery_result",
        lambda task_id: FakeAsyncResult(
            "PROGRESS",
            False,
            info={"phase": "agents", "progress": 45, "message": "summary running"},
        ),
    )

    enriched = task_status.enrich_task_dispatch({"backend": "celery", "task_id": "task-progress"})

    assert enriched == {
        "backend": "celery",
        "task_id": "task-progress",
        "state": "PROGRESS",
        "ready": False,
        "result": {"phase": "agents", "progress": 45, "message": "summary running"},
    }


def test_enrich_task_dispatch_accepts_pydantic_model_and_adds_failure_error(monkeypatch):
    monkeypatch.setattr(
        task_status,
        "_get_celery_result",
        lambda task_id: FakeAsyncResult("FAILURE", True, False, RuntimeError("worker failed")),
    )
    task = TaskDispatchInfo(backend="celery", task_id="task-2")

    enriched = task_status.enrich_task_dispatch(task)

    assert enriched == {
        "backend": "celery",
        "task_id": "task-2",
        "state": "FAILURE",
        "ready": True,
        "successful": False,
        "error": "worker failed",
    }
