"""Generic task status endpoints."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from models.task import TaskDispatchInfo
from services.task_status import get_task_status


router = APIRouter()


@router.get("/{task_id}", response_model=TaskDispatchInfo)
async def get_background_task_status(
    task_id: str,
    backend: str = Query("celery", description="Task backend name, currently celery for queued workers."),
) -> TaskDispatchInfo:
    """Return the current status for a queued background task."""

    return TaskDispatchInfo(**get_task_status(task_id, backend))


@router.get(
    "/{task_id}/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-sent event stream with queued task runtime status.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def stream_background_task_status(
    task_id: str,
    request: Request,
    backend: str = Query("celery", description="Task backend name, currently celery for queued workers."),
    interval: float = Query(1.5, ge=0.5, le=10.0),
) -> StreamingResponse:
    """Stream queued task status updates as server-sent events."""

    async def event_generator():
        last_payload = None

        while True:
            if await request.is_disconnected():
                break

            payload = get_task_status(task_id, backend)
            serialized = json.dumps(payload, ensure_ascii=False)
            if serialized != last_payload:
                yield f"event: progress\ndata: {serialized}\n\n"
                last_payload = serialized

            if payload.get("ready") is True:
                yield f"event: done\ndata: {serialized}\n\n"
                break

            if payload.get("state") == "UNKNOWN" and payload.get("error"):
                yield f"event: error\ndata: {serialized}\n\n"
                break

            await asyncio.sleep(interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
