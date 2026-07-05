"""Helpers for evidence formatting and citation validation."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from models.rag import EvidenceItem


_CITATION_RE = re.compile(r"\bS\d+\b")


def extract_citation_ids(text: str) -> List[str]:
    """Extract evidence ids such as S1 or S23 from generated text."""
    if not text:
        return []
    seen = set()
    ids: List[str] = []
    for match in _CITATION_RE.findall(text):
        if match not in seen:
            seen.add(match)
            ids.append(match)
    return ids


def validate_citations(answer: str, evidence: Iterable[Dict[str, Any] | EvidenceItem]) -> List[str]:
    """Return non-blocking warnings for missing or invalid citations."""
    evidence_ids = {
        item.id if isinstance(item, EvidenceItem) else str(item.get("id", ""))
        for item in evidence
        if item
    }
    used = extract_citation_ids(answer)
    warnings: List[str] = []
    invalid = [cid for cid in used if cid not in evidence_ids]
    if invalid:
        warnings.append(f"回答引用了不存在的证据编号: {', '.join(invalid)}")
    if evidence_ids and not used:
        warnings.append("回答未引用任何证据编号，建议使用 [S1] 这类引用标注关键信息来源。")
    return warnings


def format_evidence_context(evidence: Iterable[EvidenceItem | Dict[str, Any]]) -> str:
    """Format evidence items into a source-aware context block for LLM prompts."""
    parts: List[str] = []
    for raw in evidence:
        item = raw if isinstance(raw, EvidenceItem) else EvidenceItem.model_validate(raw)
        title = item.document_title or item.document_id or item.file_id or "unknown"
        location_bits = []
        if item.section_path:
            location_bits.append(" / ".join(item.section_path))
        if item.page is not None:
            location_bits.append(f"page {item.page}")
        elif item.metadata.get("page_start") is not None:
            page_start = item.metadata.get("page_start")
            page_end = item.metadata.get("page_end")
            if page_end is not None and page_end != page_start:
                location_bits.append(f"pages {page_start}-{page_end}")
            else:
                location_bits.append(f"page {page_start}")
        if item.chunk_index is not None:
            location_bits.append(f"chunk {item.chunk_index}")
        location = f" ({'; '.join(location_bits)})" if location_bits else ""
        content_type = item.metadata.get("content_type") or "text"
        parts.append(
            f"[{item.id}] 来源: {title}{location}\n"
            f"证据类型: {content_type}; 检索类型: {item.retrieval_type}; 分数: {item.score:.4f}\n"
            f"{item.text}"
        )
    return "\n\n".join(parts)
