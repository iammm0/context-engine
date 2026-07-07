"""Helpers for evidence formatting and citation validation."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, Iterable, List

from models.rag import EvidenceItem


_CITATION_RE = re.compile(r"\bS\d+\b")
STRUCTURED_CITATION_TYPES = {"table", "image_ocr", "ocr", "formula", "code"}


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


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return 0


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
    if image.get("text_length") is not None:
        bits.append(f"{image.get('text_length')} chars")
    if image.get("width") is not None and image.get("height") is not None:
        bits.append(f"{image.get('width')}x{image.get('height')}")
    if image.get("target"):
        bits.append(str(image.get("target")))
    if image.get("bbox"):
        bits.append(f"bbox {_compact_text(image.get('bbox'), 120)}")
    if image.get("low_confidence") is True:
        bits.append("low confidence")
    if image.get("text_preview"):
        bits.append(f"text {_compact_text(image.get('text_preview'), 120)}")
    return ", ".join(bits)


def _format_table_source_ref(source: Dict[str, Any]) -> str:
    bits: List[str] = []
    page = source.get("page")
    page_end = source.get("page_end")
    if page is not None and page_end is not None and page_end != page:
        bits.append(f"pages {page}-{page_end}")
    elif page is not None:
        bits.append(f"page {page}")
    if source.get("table_index") is not None:
        bits.append(f"table {source.get('table_index')}")
    if source.get("caption"):
        bits.append(f"caption {_compact_text(source.get('caption'), 120)}")
    elif source.get("title"):
        bits.append(f"title {_compact_text(source.get('title'), 120)}")
    if source.get("type"):
        bits.append(f"type {source.get('type')}")
    if source.get("source"):
        bits.append(str(source.get("source")))
    if source.get("target"):
        bits.append(str(source.get("target")))
    if source.get("bbox"):
        bits.append(f"bbox {_compact_text(source.get('bbox'), 120)}")
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
        sources = artifact.get("sources") if isinstance(artifact.get("sources"), list) else []
        source_refs = [_format_table_source_ref(source) for source in sources[:3] if isinstance(source, dict)]
        source_refs = [item for item in source_refs if item]
        if source_refs:
            parts.append(f"table sources: {'; '.join(source_refs)}")
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


def _format_artifact_quality_context(artifact_quality: Any) -> str:
    if not isinstance(artifact_quality, dict):
        return ""
    if artifact_quality.get("status") not in {"warn", "fail"}:
        return ""
    warnings = artifact_quality.get("warnings")
    if not isinstance(warnings, list):
        return ""
    compact_warnings = [_compact_text(item, 120) for item in warnings if str(item).strip()]
    if not compact_warnings:
        return ""
    return f"artifact质量: {'; '.join(compact_warnings[:4])}"


def _format_quality_notes_context(quality_notes: Any) -> str:
    if not isinstance(quality_notes, list):
        return ""
    compact_notes = [_compact_text(item, 120) for item in quality_notes if str(item).strip()]
    if not compact_notes:
        return ""
    return f"质量提示: {'; '.join(compact_notes[:4])}"


def _format_source_locator_context(source_locator: Any) -> str:
    if not isinstance(source_locator, dict):
        return ""
    bits: List[str] = []
    page_start = source_locator.get("page_start")
    page_end = source_locator.get("page_end")
    if page_start is not None and page_end is not None and page_end != page_start:
        bits.append(f"pages {page_start}-{page_end}")
    elif page_start is not None:
        bits.append(f"page {page_start}")
    char_start = source_locator.get("char_start")
    char_end = source_locator.get("char_end")
    if char_start is not None and char_end is not None:
        bits.append(f"chars {char_start}-{char_end}")
    if source_locator.get("has_table_source"):
        bits.append("table source refs")
    if source_locator.get("has_image_source"):
        bits.append("image source refs")
    if source_locator.get("has_bbox"):
        bits.append("bbox")
    anchor_count = source_locator.get("anchor_count")
    if anchor_count is not None:
        bits.append(f"{anchor_count} anchors")
    if not bits:
        return ""
    return f"source locator: {'; '.join(bits)}"


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


def _evidence_items(evidence: Iterable[Dict[str, Any] | EvidenceItem]) -> List[EvidenceItem]:
    items: List[EvidenceItem] = []
    for item in evidence:
        if not item:
            continue
        items.append(item if isinstance(item, EvidenceItem) else EvidenceItem.model_validate(item))
    return items


def _evidence_content_type(item: EvidenceItem) -> str:
    metadata = item.metadata or {}
    artifact = metadata.get("artifact") if isinstance(metadata.get("artifact"), dict) else {}
    return str(metadata.get("content_type") or artifact.get("type") or "text").strip().lower()


def _source_locator_anchor_count(locator: Any) -> int:
    if not isinstance(locator, dict):
        return 0
    anchors = locator.get("anchors")
    anchor_list_count = len(anchors) if isinstance(anchors, list) else 0
    return max(_safe_int(locator.get("anchor_count")), anchor_list_count, 0)


def _has_source_locator(item: EvidenceItem) -> bool:
    return _source_locator_anchor_count((item.metadata or {}).get("source_locator")) > 0


def _artifact_quality(item: EvidenceItem) -> Dict[str, Any]:
    quality = (item.metadata or {}).get("artifact_quality")
    return quality if isinstance(quality, dict) else {}


def _quality_notes(item: EvidenceItem) -> List[str]:
    notes = (item.metadata or {}).get("quality_notes")
    if not isinstance(notes, list):
        return []
    return [str(note).strip() for note in notes if str(note).strip()]


def _has_quality_notes(item: EvidenceItem) -> bool:
    return bool(_quality_notes(item))


def _artifact_quality_warns(item: EvidenceItem) -> bool:
    return str(_artifact_quality(item).get("status") or "").lower() in {"warn", "fail"}


def _has_low_confidence_ocr(item: EvidenceItem) -> bool:
    quality = _artifact_quality(item)
    if _safe_int(quality.get("ocr_low_confidence_source_count")) > 0:
        return True
    artifact = (item.metadata or {}).get("artifact")
    images = artifact.get("images") if isinstance(artifact, dict) else None
    images = images if isinstance(images, list) else []
    return any(isinstance(image, dict) and image.get("low_confidence") is True for image in images)


def _cited_risk_reasons(item: EvidenceItem) -> List[str]:
    reasons: List[str] = []
    if _evidence_content_type(item) in STRUCTURED_CITATION_TYPES and not _has_source_locator(item):
        reasons.append("missing_source_locator")
    if _artifact_quality_warns(item):
        reasons.append("artifact_warning")
    if _has_low_confidence_ocr(item):
        reasons.append("low_confidence_ocr")
    if _has_quality_notes(item):
        reasons.append("quality_note")
    return reasons


def build_citation_policy_context(
    evidence: Iterable[Dict[str, Any] | EvidenceItem],
    evidence_quality: Dict[str, Any] | None = None,
) -> str:
    """Build a compact instruction block that tells the model how to cite evidence."""
    items = _evidence_items(evidence)
    if not items:
        return (
            "引用规则:\n"
            "- 当前没有可用证据；如果资料中找不到支持信息，请明确说明“资料中未找到”。\n"
            "- 不要编造 [S1] 这类证据编号。\n"
        )

    evidence_ids = [item.id for item in items if item.id]
    structured_ids = [
        item.id
        for item in items
        if str((item.metadata or {}).get("content_type") or "").lower() in {"table", "image_ocr", "ocr", "formula", "code"}
    ]
    weak_ids = [
        item.id
        for item in items
        if (
            isinstance((item.metadata or {}).get("artifact_quality"), dict)
            and (item.metadata or {}).get("artifact_quality", {}).get("status") in {"warn", "fail"}
        )
        or _has_quality_notes(item)
    ]
    locator_ids = [
        item.id
        for item in items
        if isinstance((item.metadata or {}).get("source_locator"), dict)
        and int((item.metadata or {}).get("source_locator", {}).get("anchor_count") or 0) > 0
    ]

    lines = [
        "引用规则:",
        f"- 只能使用以下证据编号: {', '.join(evidence_ids)}。",
        "- 每个关键事实、数据、结论或对表格/OCR内容的转述后，都要紧跟至少一个证据编号，如 [S1]。",
        "- 不要编造不存在的证据编号；如果证据不足，请写明“资料中未找到”。",
        "- 如果多个证据支持同一结论，可以合并引用，如 [S1][S3]。",
    ]
    if structured_ids:
        lines.append(f"- 表格、图片/OCR、公式或代码证据包括: {', '.join(structured_ids)}；引用这些内容时要保留对应证据编号。")
    if locator_ids:
        lines.append(f"- 带原文定位的证据包括: {', '.join(locator_ids)}；优先使用这些证据支撑可核验结论。")
    if weak_ids:
        lines.append(f"- 以下证据存在解析质量提醒，引用时要谨慎表述: {', '.join(weak_ids)}。")
    if isinstance(evidence_quality, dict) and evidence_quality.get("status") in {"warn", "no_evidence"}:
        warnings = evidence_quality.get("warnings")
        if isinstance(warnings, list) and warnings:
            lines.append(f"- 证据质量提醒: {'; '.join(_compact_text(item, 120) for item in warnings[:3])}。")
    return "\n".join(lines) + "\n\n"


def _evidence_locator(item: EvidenceItem) -> Dict[str, Any]:
    metadata = item.metadata or {}
    artifact = metadata.get("artifact") if isinstance(metadata.get("artifact"), dict) else {}
    return {
        "id": item.id,
        "score": item.score,
        "document_id": item.document_id,
        "file_id": item.file_id,
        "conversation_id": item.conversation_id,
        "chunk_id": item.chunk_id,
        "chunk_index": item.chunk_index,
        "document_title": item.document_title,
        "section_path": item.section_path,
        "page": item.page,
        "page_start": metadata.get("page_start"),
        "page_end": metadata.get("page_end"),
        "content_type": metadata.get("content_type") or artifact.get("type"),
        "retrieval_type": item.retrieval_type,
        "preview": metadata.get("preview") or _compact_text(item.text, 160),
        "source_locator": metadata.get("source_locator"),
        "artifact_quality": metadata.get("artifact_quality"),
        "quality_notes": _quality_notes(item),
    }


def build_citation_diagnostics(answer: str, evidence: Iterable[Dict[str, Any] | EvidenceItem]) -> Dict[str, Any]:
    """Build structured citation coverage diagnostics for generated answers."""
    items = _evidence_items(evidence)
    evidence_ids = [item.id for item in items if item.id]
    evidence_id_set = set(evidence_ids)
    mentions = _CITATION_RE.findall(answer or "")
    mention_counts = Counter(mentions)
    used_ids = extract_citation_ids(answer)
    valid_ids = [cid for cid in used_ids if cid in evidence_id_set]
    invalid_ids = [cid for cid in used_ids if cid not in evidence_id_set]
    duplicate_ids = [cid for cid, count in mention_counts.items() if count > 1]
    unused_ids = [eid for eid in evidence_ids if eid not in set(valid_ids)]
    item_by_id = {item.id: item for item in items if item.id}
    cited_items = [item_by_id[cid] for cid in valid_ids if cid in item_by_id]
    cited_structured_items = [
        item for item in cited_items if _evidence_content_type(item) in STRUCTURED_CITATION_TYPES
    ]
    cited_missing_source_locator_ids = [
        item.id for item in cited_structured_items if item.id and not _has_source_locator(item)
    ]
    cited_artifact_warning_ids = [
        item.id for item in cited_items if item.id and _artifact_quality_warns(item)
    ]
    cited_low_confidence_ocr_ids = [
        item.id for item in cited_items if item.id and _has_low_confidence_ocr(item)
    ]
    cited_quality_note_ids = [
        item.id for item in cited_items if item.id and _has_quality_notes(item)
    ]
    cited_risky_evidence = []
    for item in cited_items:
        risk_reasons = _cited_risk_reasons(item)
        if risk_reasons:
            cited_risky_evidence.append({**_evidence_locator(item), "risk_reasons": risk_reasons})
    top_evidence = sorted(items, key=lambda item: item.score, reverse=True)[:3]
    unreferenced_top = [item for item in top_evidence if item.id and item.id not in set(valid_ids)]
    unreferenced_top_ids = [item.id for item in unreferenced_top]
    coverage = (len(valid_ids) / len(evidence_ids)) if evidence_ids else None

    warnings: List[str] = []
    recommendations: List[str] = []
    if invalid_ids:
        warnings.append(f"回答引用了不存在的证据编号: {', '.join(invalid_ids)}")
        recommendations.append("删除或替换不存在的证据编号，只使用检索结果中提供的 [Sx]。")
    if evidence_ids and not used_ids:
        warnings.append("回答未引用任何证据编号，建议使用 [S1] 这类引用标注关键信息来源。")
        recommendations.append("为每个关键事实补充至少一个证据编号。")
    if duplicate_ids:
        warnings.append(f"回答重复引用了证据编号: {', '.join(duplicate_ids)}")
        recommendations.append("合并重复引用，保留必要的证据编号即可。")
    if cited_missing_source_locator_ids:
        warnings.append(f"回答引用的结构化证据缺少统一来源定位: {', '.join(cited_missing_source_locator_ids)}")
        recommendations.append("复核缺少 source_locator 的结构化引用，必要时重新解析或改用可回源证据。")
    if cited_artifact_warning_ids:
        warnings.append(f"回答引用了存在解析质量提醒的证据: {', '.join(cited_artifact_warning_ids)}")
        recommendations.append("对带解析质量提醒的引用保持保守表述，并优先复核对应原文或 artifact。")
    if cited_low_confidence_ocr_ids:
        warnings.append(f"回答引用了低置信 OCR 证据: {', '.join(cited_low_confidence_ocr_ids)}")
        recommendations.append("低置信 OCR 引用需要人工复核图片文字，避免把识别不确定内容写成确定结论。")
    if cited_quality_note_ids:
        warnings.append(f"回答引用了带质量提示的证据: {', '.join(cited_quality_note_ids)}")
        recommendations.append("复核带质量提示的引用，必要时改用定位更完整或解析质量更高的证据。")
    if unreferenced_top_ids:
        recommendations.append(f"复核未引用的高分证据: {', '.join(unreferenced_top_ids)}。")

    if not evidence_ids:
        status = "no_evidence"
        risk_level = "high"
        recommendations.append("未检索到可引用证据，应提示用户资料中未找到或扩大检索范围。")
    elif invalid_ids:
        status = "invalid"
        risk_level = "high"
    elif not valid_ids:
        status = "missing"
        risk_level = "high"
    elif coverage == 1:
        status = "complete"
        risk_level = (
            "medium"
            if (
                duplicate_ids
                or cited_missing_source_locator_ids
                or cited_artifact_warning_ids
                or cited_low_confidence_ocr_ids
                or cited_quality_note_ids
            )
            else "low"
        )
    else:
        status = "partial"
        risk_level = "medium"

    return {
        "status": status,
        "risk_level": risk_level,
        "evidence_count": len(evidence_ids),
        "used_citation_ids": used_ids,
        "valid_citation_ids": valid_ids,
        "invalid_citation_ids": invalid_ids,
        "duplicate_citation_ids": duplicate_ids,
        "cited_structured_evidence_count": len(cited_structured_items),
        "cited_missing_source_locator_ids": cited_missing_source_locator_ids,
        "cited_artifact_warning_ids": cited_artifact_warning_ids,
        "cited_low_confidence_ocr_ids": cited_low_confidence_ocr_ids,
        "cited_quality_note_ids": cited_quality_note_ids,
        "cited_risky_evidence": cited_risky_evidence,
        "unused_evidence_ids": unused_ids,
        "unreferenced_top_evidence_ids": unreferenced_top_ids,
        "unreferenced_top_evidence": [_evidence_locator(item) for item in unreferenced_top],
        "coverage": round(coverage, 4) if coverage is not None else None,
        "warnings": warnings,
        "recommendations": recommendations,
    }


def validate_citations(answer: str, evidence: Iterable[Dict[str, Any] | EvidenceItem]) -> List[str]:
    """Return non-blocking warnings for missing or invalid citations."""
    return build_citation_diagnostics(answer, evidence).get("warnings", [])


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
        source_locator_context = _format_source_locator_context(item.metadata.get("source_locator"))
        artifact_quality_context = _format_artifact_quality_context(item.metadata.get("artifact_quality"))
        quality_notes_context = _format_quality_notes_context(item.metadata.get("quality_notes"))
        artifact_context = _format_artifact_context(item.metadata.get("artifact"))
        body_parts = [source_locator_context, artifact_quality_context, quality_notes_context, artifact_context, item.text]
        body = "\n".join(part for part in body_parts if part)
        parts.append(
            f"[{item.id}] 来源: {title}{location}\n"
            f"证据类型: {content_type}; 检索类型: {item.retrieval_type}; 分数: {item.score:.4f}\n"
            f"{body}"
        )
    return "\n\n".join(parts)
