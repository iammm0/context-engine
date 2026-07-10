"""Dispatch document processing jobs to Celery with a local fallback."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional
from urllib.parse import urlsplit, urlunsplit

from fastapi import BackgroundTasks

from utils.logger import logger


LOCAL_BACKENDS = {"background", "fastapi", "local", "inline"}


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _configured_backend() -> str:
    return os.getenv("DOCUMENT_TASK_BACKEND", "celery").strip().lower()


def _redact_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if "@" not in parsed.netloc:
            return url

        credentials, host = parsed.netloc.rsplit("@", 1)
        username = credentials.split(":", 1)[0]
        netloc = f"{username}:***@{host}" if username else host
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return "<redacted>"


def check_document_task_queue_health() -> Dict[str, Any]:
    backend = _configured_backend()
    fallback_local = _bool_env("DOCUMENT_TASK_FALLBACK_LOCAL", False)

    if backend in LOCAL_BACKENDS:
        return {
            "status": "healthy",
            "connected": True,
            "configured_backend": backend,
            "active_backend": "fastapi-background",
            "fallback_local": fallback_local,
        }

    status: Dict[str, Any] = {
        "status": "unknown",
        "connected": False,
        "configured_backend": backend,
        "active_backend": "celery",
        "fallback_local": fallback_local,
    }

    try:
        import redis
        from tasks.celery_app import broker_url, celery_app, result_backend

        status["broker_url"] = _redact_url(broker_url)
        status["result_backend"] = _redact_url(result_backend)

        redis_client = redis.Redis.from_url(
            broker_url,
            socket_connect_timeout=float(os.getenv("CELERY_HEALTH_TIMEOUT_S", "1.0")),
            socket_timeout=float(os.getenv("CELERY_HEALTH_TIMEOUT_S", "1.0")),
        )
        redis_client.ping()
        status["redis"] = "healthy"

        inspect_timeout = float(os.getenv("CELERY_HEALTH_TIMEOUT_S", "1.0"))
        workers = celery_app.control.inspect(timeout=inspect_timeout).ping() or {}
        worker_count = len(workers)
        status["worker_count"] = worker_count
        status["workers"] = ",".join(sorted(workers.keys())) if workers else ""

        if worker_count > 0:
            status["status"] = "healthy"
            status["connected"] = True
        else:
            status["status"] = "degraded"
            status["connected"] = False
            status["error"] = "No Celery workers responded to ping"
    except Exception as exc:
        status["status"] = "unhealthy"
        status["connected"] = False
        status["error"] = str(exc)[:200]

    return status


def _run_local_document_processing(
    file_path: str,
    doc_id: str,
    assistant_id: Optional[str],
    knowledge_space_id: Optional[str],
) -> None:
    from services.document_ingestion import process_document_background

    process_document_background(file_path, doc_id, assistant_id, knowledge_space_id)


def _enqueue_local(
    background_tasks: BackgroundTasks,
    file_path: str,
    doc_id: str,
    assistant_id: Optional[str],
    knowledge_space_id: Optional[str],
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    background_tasks.add_task(
        _run_local_document_processing,
        file_path,
        doc_id,
        assistant_id,
        knowledge_space_id,
    )
    payload: Dict[str, Any] = {"backend": "fastapi-background", "task_id": None}
    if reason:
        payload["fallback_reason"] = reason
    return payload


def store_document_task_dispatch(doc_repo: Any, doc_id: str, task_dispatch: Dict[str, Any]) -> None:
    try:
        doc_repo.update_document_metadata(doc_id, {"task": task_dispatch})
    except Exception:
        logger.warning(
            "Failed to persist document task dispatch metadata - document_id=%s task=%s",
            doc_id,
            task_dispatch,
            exc_info=True,
        )


def enqueue_document_processing(
    background_tasks: BackgroundTasks,
    file_path: str,
    doc_id: str,
    assistant_id: Optional[str] = None,
    knowledge_space_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Queue document processing outside the request path.

    DOCUMENT_TASK_BACKEND=celery uses Redis/Celery. Set DOCUMENT_TASK_BACKEND=local
    for local development, or set DOCUMENT_TASK_FALLBACK_LOCAL=true to opt in
    to FastAPI BackgroundTasks when Celery enqueue fails.
    """

    backend = _configured_backend()
    if backend in LOCAL_BACKENDS:
        return _enqueue_local(background_tasks, file_path, doc_id, assistant_id, knowledge_space_id)

    try:
        from tasks.document_tasks import process_document_task

        result = process_document_task.delay(file_path, doc_id, assistant_id, knowledge_space_id)
        logger.info(
            "Document processing job queued in Celery - document_id=%s task_id=%s",
            doc_id,
            result.id,
        )
        return {"backend": "celery", "task_id": result.id}
    except Exception as exc:
        if not _bool_env("DOCUMENT_TASK_FALLBACK_LOCAL", False):
            logger.error("Failed to queue Celery document job - document_id=%s", doc_id, exc_info=True)
            raise

        logger.warning(
            "Falling back to FastAPI BackgroundTasks after Celery enqueue failed - document_id=%s error=%s",
            doc_id,
            exc,
        )
        return _enqueue_local(
            background_tasks,
            file_path,
            doc_id,
            assistant_id,
            knowledge_space_id,
            reason=str(exc),
        )
