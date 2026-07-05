import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from routers import documents as documents_router


class FakeDocumentRepo:
    def get_document(self, doc_id):
        return {
            "_id": doc_id,
            "title": "Demo",
            "status": "completed",
            "metadata": {"parse_quality": {"quality_score": 100}},
        }


class FakeChunkRepo:
    def get_chunks_by_document(self, document_id):
        return [
            {
                "_id": f"chunk{i}",
                "document_id": document_id,
                "chunk_index": i,
                "text": f"chunk text {i}",
                "metadata": {"content_type": "text", "preview": f"chunk text {i}"},
            }
            for i in range(7)
        ]


@pytest.mark.asyncio
async def test_get_document_chunks_centers_window_on_target_chunk(monkeypatch):
    monkeypatch.setattr(documents_router, "get_document_repo", lambda: FakeDocumentRepo())
    monkeypatch.setattr(documents_router, "get_chunk_repo", lambda: FakeChunkRepo())

    response = await documents_router.get_document_chunks(
        "doc1",
        skip=0,
        limit=3,
        include_text=False,
        content_type=None,
        feature=None,
        q=None,
        target_chunk_id=None,
        target_chunk_index=4,
        context_window=1,
    )

    assert response.skip == 3
    assert response.target_found is True
    assert response.target_chunk_index == 4
    assert response.target_chunk_id == "chunk4"
    assert response.target_offset == 1
    assert [chunk["chunk_index"] for chunk in response.chunks] == [3, 4, 5]
    assert all("text" not in chunk for chunk in response.chunks)
