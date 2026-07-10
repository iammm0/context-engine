"""Deep research execution helpers shared by API routes and Celery workers."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable, Dict, List, Optional

from utils.logger import logger
from utils.timezone import beijing_now


ProgressCallback = Callable[[Dict[str, Any]], None]


AGENT_LABELS: Dict[str, str] = {
    "coordinator": "协调规划",
    "document_retrieval": "文档检索",
    "formula_analysis": "公式分析",
    "code_analysis": "代码分析",
    "concept_explanation": "概念解释",
    "example_generation": "示例生成",
    "summary": "综合总结",
    "exercise": "练习生成",
    "scientific_coding": "科研代码",
    "critic": "批判审查",
    "argument_analysis": "论证分析",
}


def _agent_label(agent_type: Optional[str]) -> str:
    if not agent_type:
        return "深度研究"
    return AGENT_LABELS.get(agent_type, agent_type)


def build_deep_research_markdown(agent_results: List[Dict[str, Any]], html_content: str = "") -> str:
    parts: List[str] = []
    for result in agent_results:
        content = str(result.get("content") or "").strip()
        if not content:
            continue
        title = str(result.get("title") or _agent_label(result.get("agent_type")))
        parts.append(f"## {title}\n\n{content}")

    if not parts and html_content.strip():
        return "深度研究已完成，HTML 报告已生成，可在当前会话的深度研究面板中查看。"

    return "\n\n---\n\n".join(parts)


def _get_recent_conversation_history(conversation_id: Optional[str]) -> Optional[List[Dict[str, str]]]:
    if not conversation_id:
        return None

    try:
        from database.mongodb import mongodb_client

        if mongodb_client.db is None:
            mongodb_client.connect()
        collection = mongodb_client.get_collection("conversations")
        doc = collection.find_one({"_id": conversation_id})
        if not doc:
            return None

        return [
            {"role": str(message.get("role") or ""), "content": str(message.get("content") or "")}
            for message in (doc.get("messages") or [])[-5:]
        ]
    except Exception as exc:
        logger.warning("获取深度研究对话历史失败 - conversation_id=%s error=%s", conversation_id, exc)
        return None


def _persist_deep_research_message(conversation_id: Optional[str], content: str) -> Optional[str]:
    if not conversation_id or not content.strip():
        return None

    try:
        from database.mongodb import mongodb_client

        if mongodb_client.db is None:
            mongodb_client.connect()
        collection = mongodb_client.get_collection("conversations")

        message_id = str(uuid.uuid4())
        now = beijing_now()
        result = collection.update_one(
            {"_id": conversation_id},
            {
                "$push": {
                    "messages": {
                        "message_id": message_id,
                        "role": "assistant",
                        "content": content,
                        "timestamp": now,
                        "sources": [],
                        "evidence": [],
                        "evidence_quality": None,
                        "citation_warnings": [],
                        "citation_quality": None,
                        "recommended_resources": [],
                    }
                },
                "$set": {"updated_at": now},
            },
        )
        if result.matched_count == 0:
            logger.warning("深度研究任务完成但会话不存在 - conversation_id=%s", conversation_id)
            return None
        return message_id
    except Exception as exc:
        logger.warning("保存深度研究结果到会话失败 - conversation_id=%s error=%s", conversation_id, exc, exc_info=True)
        return None


async def run_deep_research(
    query: str,
    assistant_id: Optional[str] = None,
    knowledge_space_ids: Optional[List[str]] = None,
    conversation_id: Optional[str] = None,
    enabled_agents: Optional[List[str]] = None,
    generation_config: Optional[Dict[str, Any]] = None,
    persist_message: bool = False,
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """Run the deep research workflow and return a task-friendly result."""

    from agents.builder.response_builder import ResponseBuilder
    from agents.workflow.agent_workflow import AgentWorkflow

    workflow = AgentWorkflow()
    builder = ResponseBuilder()

    context = {
        "assistant_id": assistant_id,
        "knowledge_space_ids": knowledge_space_ids,
        "conversation_id": conversation_id,
        "conversation_history": _get_recent_conversation_history(conversation_id),
        "generation_config": generation_config,
    }

    agent_results: List[Dict[str, Any]] = []
    agent_statuses: Dict[str, Dict[str, Any]] = {}
    planning_content = ""
    html_content = ""
    selected_agents: List[str] = []
    dependencies: Dict[str, List[str]] = {}
    artifact: Dict[str, Any] = {}
    run_id: Optional[str] = None

    def emit(snapshot: Dict[str, Any]) -> None:
        if progress_callback:
            progress_callback(snapshot)

    emit({"phase": "planning", "message": "正在规划深度研究任务", "progress": 5})

    async for result in workflow.execute_workflow(
        query=query,
        context=context,
        enabled_agents=enabled_agents,
        stream=True,
    ):
        event_type = result.get("type")
        run_id = result.get("run_id") or run_id

        if event_type == "planning":
            planning_content = str(result.get("content") or "")
            selected_agents = list(result.get("selected_agents") or [])
            dependencies = dict(result.get("dependencies") or {})
            emit(
                {
                    "phase": "planning",
                    "message": "深度研究规划完成",
                    "progress": 15,
                    "run_id": run_id,
                    "selected_agents": selected_agents,
                    "planning": planning_content,
                }
            )
            continue

        if event_type == "agent_status":
            agent_type = str(result.get("agent_type") or "unknown")
            agent_statuses[agent_type] = {
                "agent_type": agent_type,
                "status": result.get("status") or "running",
                "current_step": result.get("current_step"),
                "progress": result.get("progress"),
                "details": result.get("details") or result.get("reason"),
                "dependencies": result.get("dependencies") or [],
                "started_at": result.get("started_at"),
                "completed_at": result.get("completed_at"),
            }
            completed = len([status for status in agent_statuses.values() if status.get("status") in {"completed", "skipped"}])
            total = max(len(agent_statuses), len(selected_agents), 1)
            emit(
                {
                    "phase": "agents",
                    "message": f"{_agent_label(agent_type)}：{agent_statuses[agent_type]['status']}",
                    "progress": min(90, 15 + int(70 * completed / total)),
                    "run_id": run_id,
                    "agent_statuses": list(agent_statuses.values()),
                }
            )
            continue

        if event_type == "agent_result":
            agent_result = {
                "agent_type": result.get("agent_type"),
                "content": result.get("content", ""),
                "sources": result.get("sources", []),
                "evidence": result.get("evidence", []),
                "evidence_ids": result.get("evidence_ids", []),
                "claims": result.get("claims", []),
                "open_questions": result.get("open_questions", []),
                "confidence": result.get("confidence", 0.5),
                "dependencies": result.get("dependencies", []),
            }
            agent_results.append(agent_result)
            emit(
                {
                    "phase": "agents",
                    "message": f"{_agent_label(agent_result.get('agent_type'))}完成",
                    "progress": min(95, 20 + len(agent_results) * 10),
                    "run_id": run_id,
                    "agent_results": agent_results,
                    "agent_statuses": list(agent_statuses.values()),
                }
            )
            continue

        if event_type == "complete":
            agent_results = list(result.get("agent_results") or agent_results)
            selected_agents = list(result.get("selected_agents") or selected_agents)
            dependencies = dict(result.get("dependencies") or dependencies)
            artifact = dict(result.get("artifact") or {})
            html_content = builder.build_html_response(
                agent_results=agent_results,
                query=query,
                metadata={"planning": planning_content},
            )
            emit(
                {
                    "phase": "report",
                    "message": "正在生成深度研究报告",
                    "progress": 96,
                    "run_id": run_id,
                    "agent_results": agent_results,
                }
            )
            break

        if event_type == "error":
            raise RuntimeError(str(result.get("content") or "深度研究工作流失败"))

    final_content = build_deep_research_markdown(agent_results, html_content)
    message_id = _persist_deep_research_message(conversation_id, final_content) if persist_message else None

    payload = {
        "status": "finished",
        "query": query,
        "conversation_id": conversation_id,
        "run_id": run_id,
        "selected_agents": selected_agents,
        "dependencies": dependencies,
        "agent_results": agent_results,
        "html_content": html_content,
        "final_content": final_content,
        "artifact": artifact,
        "message_id": message_id,
    }
    emit({"phase": "completed", "message": "深度研究完成", "progress": 100, **payload})
    return payload


def run_deep_research_sync(**kwargs: Any) -> Dict[str, Any]:
    """Run deep research from synchronous worker contexts."""

    return asyncio.run(run_deep_research(**kwargs))
