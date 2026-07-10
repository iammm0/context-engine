"""Dispatch document processing jobs to Celery with a local fallback."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks

from utils.logger import logger


LOCAL_BACKENDS = {"background", "fastapi", "local", "inline"}


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _enqueue_local(
    background_tasks: BackgroundTasks,
    file_path: str,
    doc_id: str,
    assistant_id: Optional[str],
    knowledge_space_id: Optional[str],
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    from services.document_ingestion import process_document_background

    background_tasks.add_task(
        process_document_background,
        file_path,
        doc_id,
        assistant_id,
        knowledge_space_id,
    )
    payload: Dict[str, Any] = {"backend": "fastapi-background", "task_id": None}
    if reason:
        payload["fallback_reason"] = reason
    return payload


def enqueue_document_processing(
    background_tasks: BackgroundTasks,
    file_path: str,
    doc_id: str,
    assistant_id: Optional[str] = None,
    knowledge_space_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Queue document processing outside the request path.

    DOCUMENT_TASK_BACKEND=celery uses Redis/Celery. Set DOCUMENT_TASK_BACKEND=local
    for a development fallback that keeps the old FastAPI BackgroundTasks path.
    """

    backend = os.getenv("DOCUMENT_TASK_BACKEND", "celery").strip().lower()
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
        if not _bool_env("DOCUMENT_TASK_FALLBACK_LOCAL", True):
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
