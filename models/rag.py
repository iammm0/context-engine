"""Structured models for RAG evidence and agent orchestration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SourceInfo(BaseModel):
    """Document or attachment source surfaced with retrieved evidence."""

    title: Optional[str] = None
    content: Optional[str] = None
    chunk_id: Optional[str] = None
    chunk_index: Optional[int] = None
    evidence_id: Optional[str] = None
    document_id: Optional[str] = None
    file_id: Optional[str] = None
    conversation_id: Optional[str] = None
    score: Optional[float] = None
    source: Optional[str] = None
    retrieval_type: Optional[str] = None
    document_title: Optional[str] = None
    file_type: Optional[str] = None
    status: Optional[str] = None
    page: Optional[int] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    content_type: Optional[str] = None
    artifact: Optional[Dict[str, Any]] = None
    artifact_quality: Optional[Dict[str, Any]] = None
    source_locator: Optional[Dict[str, Any]] = None
    quality_notes: Optional[List[str]] = None
    section_path: Optional[List[str]] = None
    is_conversation_attachment: Optional[bool] = None


class RecommendedResource(BaseModel):
    """Recommended resource metadata returned alongside RAG responses."""

    resource_id: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    score: Optional[float] = None


class EvidenceItem(BaseModel):
    """Chunk-level evidence passed through retrieval, generation, and agents."""

    id: str
    text: str
    document_id: Optional[str] = None
    file_id: Optional[str] = None
    conversation_id: Optional[str] = None
    chunk_id: Optional[str] = None
    chunk_index: Optional[int] = None
    document_title: Optional[str] = None
    section_path: List[str] = Field(default_factory=list)
    page: Optional[int] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    score: float = 0.0
    retrieval_type: str = "vector"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QueryPlan(BaseModel):
    """Internal retrieval plan derived from a user query."""

    intent: str = "general"
    need_rewrite: bool = False
    need_graph: bool = True
    prefetch_k: int = 200
    final_k: int = 12
    context_budget: int = 30_000
    filters: Dict[str, Any] = Field(default_factory=dict)
    rewritten_queries: List[str] = Field(default_factory=list)
    fusion_strategy: str = "rrf"


class AgentPlan(BaseModel):
    """Validated plan returned by the coordinator."""

    selected_agents: List[str] = Field(default_factory=list)
    agent_tasks: Dict[str, str] = Field(default_factory=dict)
    dependencies: Dict[str, List[str]] = Field(default_factory=dict)
    parallel_groups: List[List[str]] = Field(default_factory=list)
    reasoning: str = ""


class AgentResultModel(BaseModel):
    """Structured result emitted by expert agents."""

    agent_type: str
    content: str = ""
    claims: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    confidence: float = 0.5
    open_questions: List[str] = Field(default_factory=list)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    error: bool = False
