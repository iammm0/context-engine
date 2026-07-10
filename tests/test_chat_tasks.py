import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from tasks import chat_tasks


class FakeUpdateResult:
    def __init__(self, matched_count):
        self.matched_count = matched_count


class FakeConversationsCollection:
    def __init__(self, document):
        self.document = document
        self.update_calls = []

    def find_one(self, query):
        if query == {"_id": self.document["_id"]}:
            return self.document
        return None

    def update_one(self, query, update):
        self.update_calls.append((query, update))
        if query.get("_id") != self.document["_id"]:
            return FakeUpdateResult(0)
        if "title" in query and query["title"] != self.document.get("title"):
            return FakeUpdateResult(0)

        self.document.update(update.get("$set", {}))
        return FakeUpdateResult(1)


def test_generate_conversation_title_updates_default_title(monkeypatch):
    document = {
        "_id": "conv1",
        "title": "新对话",
        "messages": [
            {"role": "user", "content": "帮我梳理 RAG 任务队列"},
            {"role": "assistant", "content": "可以从 Celery 开始。"},
        ],
    }
    collection = FakeConversationsCollection(document)
    monkeypatch.setattr(chat_tasks, "_get_conversations_collection", lambda: collection)

    from services import title_generator as title_generator_module

    captured = {}

    def fake_generate(messages):
        captured["messages"] = messages
        return "RAG任务队列"

    monkeypatch.setattr(title_generator_module.title_generator, "generate_conversation_title", fake_generate)

    result = chat_tasks.generate_conversation_title("conv1", "新对话")

    assert result == {"conversation_id": "conv1", "status": "finished", "title": "RAG任务队列"}
    assert document["title"] == "RAG任务队列"
    assert "updated_at" in document
    assert collection.update_calls[0][0] == {"_id": "conv1", "title": "新对话"}
    assert captured["messages"] == [
        {"role": "user", "content": "帮我梳理 RAG 任务队列"},
        {"role": "assistant", "content": "可以从 Celery 开始。"},
    ]


def test_generate_conversation_title_skips_when_title_changed(monkeypatch):
    document = {
        "_id": "conv1",
        "title": "手动标题",
        "messages": [{"role": "user", "content": "hello"}],
    }
    collection = FakeConversationsCollection(document)
    monkeypatch.setattr(chat_tasks, "_get_conversations_collection", lambda: collection)

    result = chat_tasks.generate_conversation_title("conv1", "新对话")

    assert result == {"conversation_id": "conv1", "status": "skipped", "reason": "title_changed"}
    assert document["title"] == "手动标题"
    assert collection.update_calls == []
