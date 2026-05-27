"""Structured models for RAG evidence and agent orchestration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
