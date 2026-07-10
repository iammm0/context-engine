"""Celery tasks for document ingestion."""

from __future__ import annotations

from typing import Optional

from tasks.celery_app import celery_app


@celery_app.task(name="advanced_rag.documents.process", bind=True)
def process_document_task(
    self,
    file_path: str,
    doc_id: str,
    assistant_id: Optional[str] = None,
    knowledge_space_id: Optional[str] = None,
) -> dict:
    """Run document processing in a Celery worker process."""

    from routers.documents import process_document_background

    process_document_background(
        file_path=file_path,
        doc_id=doc_id,
        assistant_id=assistant_id,
        knowledge_space_id=knowledge_space_id,
    )
    return {"document_id": doc_id, "task_id": self.request.id, "status": "finished"}

