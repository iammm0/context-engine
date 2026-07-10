"""Celery application configuration for context-engine workers."""

from __future__ import annotations

import os

from celery import Celery


def _redis_url(db: str) -> str:
    host = os.getenv("REDIS_HOST", "localhost")
    port = os.getenv("REDIS_PORT", "6379")
    return f"redis://{host}:{port}/{db}"


broker_url = os.getenv("CELERY_BROKER_URL") or _redis_url(os.getenv("REDIS_DB", "0"))
result_backend = os.getenv("CELERY_RESULT_BACKEND") or _redis_url(os.getenv("CELERY_RESULT_DB", "1"))

celery_app = Celery(
    "advanced_rag",
    broker=broker_url,
    backend=result_backend,
    include=["tasks.document_tasks", "tasks.chat_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_prefetch_multiplier=int(os.getenv("CELERY_WORKER_PREFETCH_MULTIPLIER", "1")),
    task_acks_late=os.getenv("CELERY_TASK_ACKS_LATE", "true").lower() in {"1", "true", "yes"},
)
