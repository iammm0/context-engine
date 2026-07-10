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


class FakePreviewDocumentRepo:
    def __init__(self, file_path):
        self.file_path = file_path

    def get_document(self, doc_id):
        return {
            "_id": doc_id,
            "title": "Demo.pdf",
            "status": "completed",
            "file_type": "pdf",
            "file_path": str(self.file_path),
            "metadata": {},
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


class FakeMixedChunkRepo:
    def get_chunks_by_document(self, document_id):
        return [
            {
                "_id": "text0",
                "document_id": document_id,
                "chunk_index": 0,
                "text": "text chunk",
                "metadata": {"content_type": "text", "preview": "text chunk"},
            },
            {
                "_id": "table1",
                "document_id": document_id,
                "chunk_index": 1,
                "text": "complete table",
                "metadata": {
                    "content_type": "table",
                    "preview": "complete table",
                    "artifact": {
                        "type": "table",
                        "headers": ["Metric"],
                        "rows": [["Recall"]],
                        "sources": [{"page": 1, "table_index": 1}],
                    },
                },
            },
            {
                "_id": "table3",
                "document_id": document_id,
                "chunk_index": 3,
                "text": "table without source",
                "metadata": {
                    "content_type": "table",
                    "preview": "table without source",
                    "artifact": {"type": "table", "headers": ["Metric"], "rows": [["Precision"]]},
                },
            },
            {
                "_id": "table4",
                "document_id": document_id,
                "chunk_index": 4,
                "text": "target table without source",
                "metadata": {
                    "content_type": "table",
                    "preview": "target table without source",
                    "artifact": {"type": "table", "headers": ["Metric"], "rows": [["F1"]]},
                },
            },
        ]


class FakeProgressDocumentRepo:
    def get_document(self, doc_id):
        return {
            "_id": doc_id,
            "status": "completed",
            "progress_percentage": 100,
            "current_stage": "完成",
            "stage_details": "done",
        }


class FakeRequest:
    async def is_disconnected(self):
        return False


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


@pytest.mark.asyncio
async def test_get_document_chunks_falls_back_to_target_index_when_chunk_id_is_stale(monkeypatch):
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
        target_chunk_id="stale-retrieval-id",
        target_chunk_index=4,
        context_window=1,
    )

    assert response.skip == 3
    assert response.target_found is True
    assert response.target_chunk_index == 4
    assert response.target_chunk_id == "chunk4"
    assert response.target_offset == 1
    assert [chunk["chunk_index"] for chunk in response.chunks] == [3, 4, 5]


@pytest.mark.asyncio
async def test_get_document_chunks_centers_target_inside_filtered_artifact_issue(monkeypatch):
    monkeypatch.setattr(documents_router, "get_document_repo", lambda: FakeDocumentRepo())
    monkeypatch.setattr(documents_router, "get_chunk_repo", lambda: FakeMixedChunkRepo())

    response = await documents_router.get_document_chunks(
        "doc1",
        skip=0,
        limit=1,
        include_text=False,
        content_type="table",
        feature="table_missing_source",
        q=None,
        target_chunk_id=None,
        target_chunk_index=4,
        context_window=0,
    )

    assert response.skip == 1
    assert response.total_chunks == 2
    assert response.total_all_chunks == 4
    assert response.target_found is True
    assert response.target_chunk_index == 4
    assert response.target_chunk_id == "table4"
    assert response.target_offset == 0
    assert response.filters == {"content_type": "table", "feature": "table_missing_source", "q": None}
    assert response.facets["content_type_counts"] == {"table": 3, "text": 1}
    assert response.facets["feature_counts"]["artifact_issue"] == 2
    assert response.facets["feature_counts"]["table_missing_source"] == 2
    assert response.facets["quality_note_count"] >= 2
    assert response.facets["problem_chunk_count"] >= 2
    assert [chunk["chunk_index"] for chunk in response.chunks] == [4]
    assert response.chunks[0]["features"]["has_table_missing_source"] is True


@pytest.mark.asyncio
async def test_preview_document_serves_original_file_inline(monkeypatch, tmp_path):
    file_path = tmp_path / "demo.pdf"
    file_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(documents_router, "get_document_repo", lambda: FakePreviewDocumentRepo(file_path))

    response = await documents_router.preview_document("doc1")

    assert response.media_type == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline;")


@pytest.mark.asyncio
async def test_stream_document_progress_emits_progress_and_done(monkeypatch):
    monkeypatch.setattr(documents_router, "get_document_repo", lambda: FakeProgressDocumentRepo())

    response = await documents_router.stream_document_progress("doc1", FakeRequest(), interval=0.5)
    events = []
    async for chunk in response.body_iterator:
        events.append(chunk.decode() if isinstance(chunk, bytes) else chunk)

    body = "".join(events)
    assert "event: progress" in body
    assert "event: done" in body
    assert '"progress_percentage": 100' in body
