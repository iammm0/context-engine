import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from routers import task_status as task_status_router


class FakeRequest:
    async def is_disconnected(self):
        return False


@pytest.mark.asyncio
async def test_get_background_task_status(monkeypatch):
    monkeypatch.setattr(
        task_status_router,
        "get_task_status",
        lambda task_id, backend: {
            "backend": backend,
            "task_id": task_id,
            "state": "STARTED",
            "ready": False,
        },
    )

    response = await task_status_router.get_background_task_status("task-1", backend="celery")

    assert response.backend == "celery"
    assert response.task_id == "task-1"
    assert response.state == "STARTED"
    assert response.ready is False


@pytest.mark.asyncio
async def test_stream_background_task_status_emits_done(monkeypatch):
    monkeypatch.setattr(
        task_status_router,
        "get_task_status",
        lambda task_id, backend: {
            "backend": backend,
            "task_id": task_id,
            "state": "SUCCESS",
            "ready": True,
            "successful": True,
        },
    )

    response = await task_status_router.stream_background_task_status(
        "task-1",
        FakeRequest(),
        backend="celery",
        interval=0.5,
    )
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    body = "".join(chunks)
    assert "event: progress" in body
    assert "event: done" in body
    assert '"state": "SUCCESS"' in body
