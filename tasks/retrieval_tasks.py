"""Celery tasks for retrieval-side preprocessing."""

from __future__ import annotations

from typing import Any, Dict

from services.query_analyzer import query_analyzer
from tasks.celery_app import celery_app


def analyze_query(query: str) -> Dict[str, Any]:
    """Run query analysis in a worker and normalize the public response shape."""

    result = query_analyzer.analyze(query)
    return {
        "need_retrieval": bool(result.get("need_retrieval", True)),
        "reason": str(result.get("reason") or "未提供理由"),
        "confidence": str(result.get("confidence") or "medium"),
    }


@celery_app.task(name="advanced_rag.retrieval.analyze_query")
def analyze_query_task(query: str) -> Dict[str, Any]:
    return analyze_query(query)
