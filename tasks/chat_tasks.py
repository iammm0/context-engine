"""Celery tasks for chat side effects."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from tasks.celery_app import celery_app
from utils.logger import logger
from utils.timezone import beijing_now


DEFAULT_CONVERSATION_TITLES = {"新对话", "新对话..."}


def _should_generate_title(title: Optional[str]) -> bool:
    current_title = (title or "").strip()
    return not current_title or current_title in DEFAULT_CONVERSATION_TITLES or len(current_title) <= 5


def _format_title_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return [
        {
            "role": str(message.get("role", "")),
            "content": str(message.get("content", "")),
        }
        for message in messages
    ]


def _get_conversations_collection():
    from database.mongodb import mongodb_client

    if mongodb_client.db is None:
        mongodb_client.connect()
    return mongodb_client.get_collection("conversations")


def generate_conversation_title(conversation_id: str, expected_title: Optional[str] = None) -> Dict[str, Any]:
    """Generate and persist a conversation title outside the API process."""

    collection = _get_conversations_collection()
    conversation = collection.find_one({"_id": conversation_id})
    if not conversation:
        return {"conversation_id": conversation_id, "status": "not_found"}

    current_title = conversation.get("title", "")
    if expected_title is not None and current_title != expected_title:
        return {"conversation_id": conversation_id, "status": "skipped", "reason": "title_changed"}

    if not _should_generate_title(current_title):
        return {"conversation_id": conversation_id, "status": "skipped", "reason": "title_not_default"}

    from services.title_generator import title_generator

    messages = _format_title_messages(conversation.get("messages", []))
    new_title = title_generator.generate_conversation_title(messages)

    update_filter: Dict[str, Any] = {"_id": conversation_id}
    if expected_title is not None:
        update_filter["title"] = expected_title

    result = collection.update_one(
        update_filter,
        {"$set": {"title": new_title, "updated_at": beijing_now()}},
    )
    if result.matched_count == 0:
        return {"conversation_id": conversation_id, "status": "skipped", "reason": "title_changed"}

    logger.info(
        "Conversation title generated - conversation_id=%s title=%s",
        conversation_id,
        new_title,
    )
    return {"conversation_id": conversation_id, "status": "finished", "title": new_title}


@celery_app.task(name="advanced_rag.chat.generate_title")
def generate_conversation_title_task(conversation_id: str, expected_title: Optional[str] = None) -> Dict[str, Any]:
    return generate_conversation_title(conversation_id, expected_title)
