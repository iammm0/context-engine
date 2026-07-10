import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from agents.builder import response_builder as response_builder_module
from agents.workflow import agent_workflow as agent_workflow_module
from services import deep_research_service


class FakeAgentWorkflow:
    async def execute_workflow(self, query, context, enabled_agents=None, stream=False):
        assert query == "compare reranking strategies"
        assert context["knowledge_space_ids"] == ["space-1"]
        assert enabled_agents == ["document_retrieval"]
        assert stream is True

        yield {
            "type": "planning",
            "run_id": "run-1",
            "content": "Use retrieval and summary agents.",
            "selected_agents": ["document_retrieval"],
            "dependencies": {},
        }
        yield {
            "type": "agent_status",
            "run_id": "run-1",
            "agent_type": "document_retrieval",
            "status": "running",
            "progress": 25,
            "details": "retrieving",
        }
        yield {
            "type": "agent_result",
            "run_id": "run-1",
            "agent_type": "document_retrieval",
            "content": "BM25 plus vector retrieval improves recall.",
            "sources": [{"title": "retrieval note"}],
            "confidence": 0.8,
        }
        yield {
            "type": "complete",
            "run_id": "run-1",
            "agent_results": [
                {
                    "agent_type": "document_retrieval",
                    "content": "BM25 plus vector retrieval improves recall.",
                    "sources": [{"title": "retrieval note"}],
                    "confidence": 0.8,
                }
            ],
            "selected_agents": ["document_retrieval"],
            "dependencies": {},
            "artifact": {"query": query},
        }


class FakeResponseBuilder:
    def build_html_response(self, agent_results, query, metadata=None):
        assert len(agent_results) == 1
        assert query == "compare reranking strategies"
        assert metadata == {"planning": "Use retrieval and summary agents."}
        return "<html>deep report</html>"


@pytest.mark.asyncio
async def test_run_deep_research_collects_task_progress(monkeypatch):
    monkeypatch.setattr(agent_workflow_module, "AgentWorkflow", FakeAgentWorkflow)
    monkeypatch.setattr(response_builder_module, "ResponseBuilder", FakeResponseBuilder)

    snapshots = []

    result = await deep_research_service.run_deep_research(
        query="compare reranking strategies",
        knowledge_space_ids=["space-1"],
        enabled_agents=["document_retrieval"],
        progress_callback=snapshots.append,
    )

    assert result["status"] == "finished"
    assert result["run_id"] == "run-1"
    assert result["html_content"] == "<html>deep report</html>"
    assert result["message_id"] is None
    assert "BM25 plus vector retrieval improves recall." in result["final_content"]
    assert [snapshot["phase"] for snapshot in snapshots] == [
        "planning",
        "planning",
        "agents",
        "agents",
        "report",
        "completed",
    ]
    assert snapshots[-1]["progress"] == 100
    assert snapshots[-1]["final_content"] == result["final_content"]
