"""Celery tasks for deep research workflows."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from tasks.celery_app import celery_app


@celery_app.task(name="advanced_rag.chat.deep_research", bind=True)
def deep_research_task(
    self,
    query: str,
    assistant_id: Optional[str] = None,
    knowledge_space_ids: Optional[List[str]] = None,
    conversation_id: Optional[str] = None,
    enabled_agents: Optional[List[str]] = None,
    generation_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run deep research in a Celery worker and persist the final assistant message."""

    from services.deep_research_service import run_deep_research_sync

    def update_progress(snapshot: Dict[str, Any]) -> None:
        self.update_state(state="PROGRESS", meta=snapshot)

    return run_deep_research_sync(
        query=query,
        assistant_id=assistant_id,
        knowledge_space_ids=knowledge_space_ids,
        conversation_id=conversation_id,
        enabled_agents=enabled_agents,
        generation_config=generation_config,
        persist_message=True,
        progress_callback=update_progress,
    )
