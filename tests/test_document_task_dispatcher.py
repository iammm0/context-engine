import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from services.document_task_dispatcher import enqueue_document_processing


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append((func, args, kwargs))


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
    _, args, kwargs = background_tasks.tasks[0]
    assert args == ("uploads/demo.pdf", "doc1", "assistant1", "space1")
    assert kwargs == {}
