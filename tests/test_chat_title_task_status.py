import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from routers import chat
from tasks import chat_tasks


class FakeUpdateResult:
    matched_count = 1


class FakeCollection:
    def __init__(self, document):
        self.document = document
        self.updates = []

    async def find_one(self, query):
        assert query == {"_id": self.document["_id"]}
        return self.document

    async def update_one(self, query, update):
        assert query == {"_id": self.document["_id"]}
        self.updates.append(update)
        if "$set" in update:
            self.document.update(update["$set"])
        if "$push" in update and "messages" in update["$push"]:
            self.document.setdefault("messages", []).append(update["$push"]["messages"])
        return FakeUpdateResult()


class FakeQueuedTask:
    id = "title-task-1"


class FakeTitleTask:
    def delay(self, conversation_id, expected_title):
        assert conversation_id == "conv1"
        assert expected_title == "abc"
        return FakeQueuedTask()


@pytest.mark.asyncio
async def test_add_assistant_message_persists_title_task(monkeypatch):
    collection = FakeCollection(
        {
            "_id": "conv1",
            "title": "abc",
            "messages": [],
        }
    )

    monkeypatch.setattr(chat.mongodb, "get_collection", lambda name: collection)
    monkeypatch.setattr(chat_tasks, "generate_conversation_title_task", FakeTitleTask())

    response = await chat.add_message(
        "conv1",
        chat.MessageAdd(role="assistant", content="assistant answer"),
        None,
    )

    assert response["success"] is True
    assert collection.document["title_task"] == {
        "backend": "celery",
        "task_id": "title-task-1",
    }
    assert any("title_task" in update.get("$set", {}) for update in collection.updates)
