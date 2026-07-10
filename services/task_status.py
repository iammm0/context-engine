"""Runtime status helpers for queued background tasks."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def _as_task_dict(task_dispatch: Any) -> Optional[Dict[str, Any]]:
    if task_dispatch is None:
        return None
    if hasattr(task_dispatch, "model_dump"):
        return task_dispatch.model_dump(exclude_none=True)
    if isinstance(task_dispatch, Mapping):
        return dict(task_dispatch)
    return None


def _compact_result(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return {"value": str(value)[:500]}


def _get_celery_result(task_id: str):
    from tasks.celery_app import celery_app

    return celery_app.AsyncResult(task_id)


def enrich_task_dispatch(task_dispatch: Any) -> Optional[Dict[str, Any]]:
    """Attach live Celery state to stored task dispatch metadata."""

    payload = _as_task_dict(task_dispatch)
    if not payload:
        return None

    if payload.get("backend") != "celery" or not payload.get("task_id"):
        return payload

    try:
        async_result = _get_celery_result(str(payload["task_id"]))
        state = async_result.state
        ready = async_result.ready()
        payload["state"] = state
        payload["ready"] = ready

        if ready:
            successful = async_result.successful()
            payload["successful"] = successful
            if successful:
                result = _compact_result(async_result.result)
                if result is not None:
                    payload["result"] = result
            elif async_result.result is not None:
                payload["error"] = str(async_result.result)[:500]
    except Exception as exc:
        payload["state"] = payload.get("state") or "UNKNOWN"
        payload["error"] = str(exc)[:500]

    return payload
