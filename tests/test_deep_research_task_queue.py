import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from routers import chat
from tasks import deep_research_tasks


class FakeQueuedTask:
    id = "deep-task-1"


class FakeDeepResearchTask:
    def __init__(self):
        self.calls = []

    def delay(
        self,
        query,
        assistant_id,
        knowledge_space_ids,
        conversation_id,
        enabled_agents,
        generation_config,
    ):
        self.calls.append(
            {
                "query": query,
                "assistant_id": assistant_id,
                "knowledge_space_ids": knowledge_space_ids,
                "conversation_id": conversation_id,
                "enabled_agents": enabled_agents,
                "generation_config": generation_config,
            }
        )
        return FakeQueuedTask()


class FailingDeepResearchTask:
    def delay(self, *args, **kwargs):
        raise RuntimeError("broker down")


@pytest.mark.asyncio
async def test_queue_deep_research_task_returns_celery_dispatch(monkeypatch):
    fake_task = FakeDeepResearchTask()
    monkeypatch.setattr(deep_research_tasks, "deep_research_task", fake_task)

    response = await chat.queue_deep_research_task(
        chat.DeepResearchRequest(
            query="compare reranking strategies",
            assistant_id="assistant-1",
            knowledge_space_ids=["space-1"],
            conversation_id="conv-1",
            enabled_agents=["document_retrieval", "summary"],
            generation_config={"llm_model": "demo-model"},
        ),
        None,
    )

    assert response.backend == "celery"
    assert response.task_id == "deep-task-1"
    assert fake_task.calls == [
        {
            "query": "compare reranking strategies",
            "assistant_id": "assistant-1",
            "knowledge_space_ids": ["space-1"],
            "conversation_id": "conv-1",
            "enabled_agents": ["document_retrieval", "summary"],
            "generation_config": {"llm_model": "demo-model"},
        }
    ]


@pytest.mark.asyncio
async def test_queue_deep_research_task_failure_returns_503(monkeypatch):
    monkeypatch.setattr(deep_research_tasks, "deep_research_task", FailingDeepResearchTask())

    with pytest.raises(chat.HTTPException) as exc_info:
        await chat.queue_deep_research_task(
            chat.DeepResearchRequest(
                query="compare reranking strategies",
                assistant_id="assistant-1",
                knowledge_space_ids=["space-1"],
                conversation_id="conv-1",
            ),
            None,
        )

    assert exc_info.value.status_code == 503
    assert "投递深度研究任务失败" in exc_info.value.detail
