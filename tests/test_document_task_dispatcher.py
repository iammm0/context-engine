import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from tasks import document_tasks
from services.document_task_dispatcher import (
    check_document_task_queue_health,
    enqueue_document_processing,
    store_document_task_dispatch,
)


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append((func, args, kwargs))


class FakeDocumentRepository:
    def __init__(self):
        self.metadata_updates = []

    def update_document_metadata(self, doc_id, metadata_patch):
        self.metadata_updates.append((doc_id, metadata_patch))


class FailingDocumentTask:
    def delay(self, *args, **kwargs):
        raise RuntimeError("queue down")


def test_enqueue_document_processing_local_backend(monkeypatch):
    monkeypatch.setenv("DOCUMENT_TASK_BACKEND", "local")

    background_tasks = FakeBackgroundTasks()
    dispatch = enqueue_document_processing(
        background_tasks,
        "uploads/demo.pdf",
        "doc1",
        "assistant1",
        "space1",
    )

    assert dispatch == {"backend": "fastapi-background", "task_id": None}
    assert len(background_tasks.tasks) == 1
    func, args, kwargs = background_tasks.tasks[0]
    assert func.__module__ == "services.document_task_dispatcher"
    assert func.__name__ == "_run_local_document_processing"
    assert args == ("uploads/demo.pdf", "doc1", "assistant1", "space1")
    assert kwargs == {}


def test_enqueue_document_processing_requires_explicit_local_fallback(monkeypatch):
    monkeypatch.setenv("DOCUMENT_TASK_BACKEND", "celery")
    monkeypatch.delenv("DOCUMENT_TASK_FALLBACK_LOCAL", raising=False)
    monkeypatch.setattr(document_tasks, "process_document_task", FailingDocumentTask())

    background_tasks = FakeBackgroundTasks()
    with pytest.raises(RuntimeError, match="queue down"):
        enqueue_document_processing(
            background_tasks,
            "uploads/demo.pdf",
            "doc1",
            "assistant1",
            "space1",
        )

    assert background_tasks.tasks == []


def test_enqueue_document_processing_fallback_local_is_opt_in(monkeypatch):
    monkeypatch.setenv("DOCUMENT_TASK_BACKEND", "celery")
    monkeypatch.setenv("DOCUMENT_TASK_FALLBACK_LOCAL", "true")
    monkeypatch.setattr(document_tasks, "process_document_task", FailingDocumentTask())

    background_tasks = FakeBackgroundTasks()
    dispatch = enqueue_document_processing(
        background_tasks,
        "uploads/demo.pdf",
        "doc1",
        "assistant1",
        "space1",
    )

    assert dispatch == {
        "backend": "fastapi-background",
        "task_id": None,
        "fallback_reason": "queue down",
    }
    assert len(background_tasks.tasks) == 1


def test_document_task_queue_health_local_backend(monkeypatch):
    monkeypatch.setenv("DOCUMENT_TASK_BACKEND", "local")

    status = check_document_task_queue_health()

    assert status["status"] == "healthy"
    assert status["connected"] is True
    assert status["active_backend"] == "fastapi-background"


def test_store_document_task_dispatch_persists_metadata():
    repo = FakeDocumentRepository()
    dispatch = {"backend": "celery", "task_id": "task-1"}

    store_document_task_dispatch(repo, "doc1", dispatch)

    assert repo.metadata_updates == [("doc1", {"task": dispatch})]
