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


class EvidenceArtifactQuality(BaseModel):
    """Per-evidence structured artifact quality diagnostics."""

    status: str = ""
    risk_level: str = ""
    structured: bool = False
    content_type: str = ""
    artifact_type: str = ""
    has_artifact: bool = False
    table_missing_structure: bool = False
    table_missing_source: bool = False
    ocr_missing_source: bool = False
    ocr_low_confidence_source_count: int = 0
    ocr_avg_confidence: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class EvidenceQuality(BaseModel):
    """Aggregate diagnostics for retrieved evidence quality."""

    status: str = ""
    risk_level: str = ""
    evidence_count: int = 0
    artifact_count: int = 0
    artifact_coverage: Optional[float] = None
    structured_evidence_count: int = 0
    structured_artifact_count: int = 0
    structured_artifact_coverage: Optional[float] = None
    source_locator_count: int = 0
    source_locator_coverage: Optional[float] = None
    structured_source_locator_count: int = 0
    structured_source_locator_coverage: Optional[float] = None
    missing_source_locator_count: int = 0
    structured_missing_source_locator_count: int = 0
    bbox_source_locator_count: int = 0
    table_source_locator_count: int = 0
    ocr_source_locator_count: int = 0
    source_anchor_count: int = 0
    table_count: int = 0
    table_missing_structure_count: int = 0
    table_missing_source_count: int = 0
    ocr_count: int = 0
    ocr_missing_source_count: int = 0
    ocr_low_confidence_source_count: int = 0
    ocr_avg_confidence: Optional[float] = None
    content_type_counts: Dict[str, int] = Field(default_factory=dict)
    artifact_type_counts: Dict[str, int] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


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


class CitationEvidenceRef(BaseModel):
    """Evidence locator included in citation diagnostics."""

    id: str
    score: Optional[float] = None
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
    content_type: Optional[str] = None
    retrieval_type: Optional[str] = None
    preview: Optional[str] = None
    source_locator: Optional[Dict[str, Any]] = None
    artifact_quality: Optional[EvidenceArtifactQuality] = None
    quality_notes: List[str] = Field(default_factory=list)
    risk_reasons: List[str] = Field(default_factory=list)


class CitationEvidenceAudit(BaseModel):
    """Per-evidence citation audit summary."""

    id: str
    content_type: Optional[str] = None
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    chunk_index: Optional[int] = None
    page: Optional[int] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    score: Optional[float] = None
    retrieval_type: Optional[str] = None
    has_source_locator: bool = False
    source_anchor_count: int = 0
    has_table_source: bool = False
    has_image_source: bool = False
    has_bbox: bool = False
    artifact_quality_status: Optional[str] = None
    risk_reasons: List[str] = Field(default_factory=list)
    quality_notes: List[str] = Field(default_factory=list)


class CitationQuality(BaseModel):
    """Citation coverage diagnostics for generated answers."""

    status: str = ""
    risk_level: str = ""
    evidence_count: int = 0
    used_citation_ids: List[str] = Field(default_factory=list)
    valid_citation_ids: List[str] = Field(default_factory=list)
    invalid_citation_ids: List[str] = Field(default_factory=list)
    duplicate_citation_ids: List[str] = Field(default_factory=list)
    cited_structured_evidence_count: int = 0
    cited_missing_source_locator_ids: List[str] = Field(default_factory=list)
    cited_artifact_warning_ids: List[str] = Field(default_factory=list)
    cited_low_confidence_ocr_ids: List[str] = Field(default_factory=list)
    cited_quality_note_ids: List[str] = Field(default_factory=list)
    evidence_citation_audit: List[CitationEvidenceAudit] = Field(default_factory=list)
    cited_risky_evidence: List[CitationEvidenceRef] = Field(default_factory=list)
    unused_evidence_ids: List[str] = Field(default_factory=list)
    unreferenced_top_evidence_ids: List[str] = Field(default_factory=list)
    unreferenced_top_evidence: List[CitationEvidenceRef] = Field(default_factory=list)
    coverage: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


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
