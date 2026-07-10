import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from routers import retrieval as retrieval_router
from tasks import retrieval_tasks


def test_analyze_query_task_normalizes_analyzer_result(monkeypatch):
    class FakeAnalyzer:
        def analyze(self, query):
            assert query == "怎么优化 RAG 检索链路"
            return {
                "need_retrieval": 1,
                "reason": "需要参考知识库",
                "confidence": "high",
            }

    monkeypatch.setattr(retrieval_tasks, "query_analyzer", FakeAnalyzer())

    result = retrieval_tasks.analyze_query("怎么优化 RAG 检索链路")

    assert result == {
        "need_retrieval": True,
        "reason": "需要参考知识库",
        "confidence": "high",
    }


@pytest.mark.asyncio
async def test_queue_query_analysis_returns_task_dispatch(monkeypatch):
    calls = []

    class FakeAsyncResult:
        id = "analysis-task-1"

    class FakeTask:
        def delay(self, query):
            calls.append(query)
            return FakeAsyncResult()

    monkeypatch.setattr(retrieval_tasks, "analyze_query_task", FakeTask())

    response = await retrieval_router.queue_query_analysis(
        retrieval_router.QueryAnalysisRequest(query="需要检索吗")
    )

    assert calls == ["需要检索吗"]
    assert response.backend == "celery"
    assert response.task_id == "analysis-task-1"
    assert response.ready is False
