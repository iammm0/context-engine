"""Helpers for evidence formatting and citation validation."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from models.rag import EvidenceItem


_CITATION_RE = re.compile(r"\bS\d+\b")


def _compact_text(value: Any, max_chars: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def _format_number(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return str(value)
    return str(value) if value is not None else ""


def _format_ocr_image_ref(image: Dict[str, Any]) -> str:
    bits: List[str] = []
    if image.get("page") is not None:
        bits.append(f"page {image.get('page')}")
    if image.get("image_index") is not None:
        bits.append(f"image {image.get('image_index')}")
    if image.get("confidence") is not None:
        confidence = image.get("confidence")
        if isinstance(confidence, (int, float)) and confidence <= 1:
            confidence = confidence * 100
        bits.append(f"confidence {_format_number(confidence)}%")
    if image.get("line_count") is not None:
        bits.append(f"{image.get('line_count')} lines")
    if image.get("width") is not None and image.get("height") is not None:
        bits.append(f"{image.get('width')}x{image.get('height')}")
    return ", ".join(bits)


def _format_artifact_context(artifact: Any) -> str:
    if not isinstance(artifact, dict):
        return ""

    artifact_type = str(artifact.get("type") or "").lower()
    if artifact_type == "table":
        parts = ["结构化证据: table"]
        headers = [str(item) for item in artifact.get("headers") or [] if item is not None]
        if headers:
            parts.append(f"列: {', '.join(headers[:8])}")
        if artifact.get("row_count") is not None:
            parts.append(f"行数: {artifact.get('row_count')}")
        if artifact.get("column_count") is not None:
            parts.append(f"列数: {artifact.get('column_count')}")
        rows = artifact.get("rows") if isinstance(artifact.get("rows"), list) else []
        row_samples = []
        for row in rows[:3]:
            if isinstance(row, list):
                row_samples.append(" | ".join(_compact_text(cell, 80) for cell in row[:8]))
        if row_samples:
            parts.append(f"样例行: {'; '.join(row_samples)}")
        elif artifact.get("markdown"):
            parts.append(f"表格预览: {_compact_text(artifact.get('markdown'))}")
        return "; ".join(parts)

    if artifact_type in {"image_ocr", "ocr"}:
        parts = [f"结构化证据: {artifact_type}"]
        if artifact.get("image_count") is not None:
            parts.append(f"图片数: {artifact.get('image_count')}")
        images = artifact.get("images") if isinstance(artifact.get("images"), list) else []
        image_refs = [_format_ocr_image_ref(image) for image in images[:3] if isinstance(image, dict)]
        image_refs = [item for item in image_refs if item]
        if image_refs:
            parts.append(f"图片来源: {'; '.join(image_refs)}")
        if artifact.get("text"):
            parts.append(f"OCR文本: {_compact_text(artifact.get('text'))}")
        return "; ".join(parts)

    if artifact_type in {"formula", "code"} and artifact.get("text"):
        return f"结构化证据: {artifact_type}; 内容: {_compact_text(artifact.get('text'))}"

    return ""


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
        artifact_context = _format_artifact_context(item.metadata.get("artifact"))
        body = f"{artifact_context}\n{item.text}" if artifact_context else item.text
        parts.append(
            f"[{item.id}] 来源: {title}{location}\n"
            f"证据类型: {content_type}; 检索类型: {item.retrieval_type}; 分数: {item.score:.4f}\n"
            f"{body}"
        )
    return "\n\n".join(parts)
