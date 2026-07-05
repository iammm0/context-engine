"""Runtime diagnostics for retrieved evidence artifacts."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from models.rag import EvidenceItem


STRUCTURED_EVIDENCE_TYPES = {"table", "image_ocr", "ocr", "formula", "code"}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _metadata(item: EvidenceItem | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(item, EvidenceItem):
        return item.metadata or {}
    return _as_dict(item.get("metadata"))


def _content_type(item: EvidenceItem | Dict[str, Any], artifact: Optional[Dict[str, Any]]) -> str:
    metadata = _metadata(item)
    value = metadata.get("content_type") or (artifact or {}).get("type")
    return str(value or "text").strip().lower()


def _artifact(item: EvidenceItem | Dict[str, Any]) -> Optional[Dict[str, Any]]:
    metadata = _metadata(item)
    artifact = metadata.get("artifact")
    return artifact if isinstance(artifact, dict) else None


def _has_table_structure(artifact: Dict[str, Any]) -> bool:
    headers = artifact.get("headers")
    rows = artifact.get("rows")
    markdown = artifact.get("markdown")
    has_headers = isinstance(headers, list) and len(headers) > 0
    has_rows = isinstance(rows, list) and len(rows) > 0
    return bool(has_headers and (has_rows or markdown))


def _artifact_type(artifact: Optional[Dict[str, Any]], content_type: str) -> str:
    return str((artifact or {}).get("type") or content_type or "text").strip().lower()


def _ocr_confidences(images: Iterable[Any]) -> List[float]:
    values: List[float] = []
    for image in images:
        if not isinstance(image, dict):
            continue
        confidence = image.get("confidence")
        if isinstance(confidence, (int, float)):
            values.append(float(confidence))
    return values


def build_evidence_quality_diagnostics(
    evidence: Iterable[EvidenceItem | Dict[str, Any]],
) -> Dict[str, Any]:
    """Summarize structured artifact completeness for retrieved evidence."""
    items = [item for item in evidence if item]
    evidence_count = len(items)
    artifact_count = 0
    structured_count = 0
    structured_with_artifact_count = 0
    table_count = 0
    table_missing_structure_count = 0
    table_missing_source_count = 0
    ocr_count = 0
    ocr_missing_source_count = 0
    ocr_low_confidence_source_count = 0
    ocr_confidence_values: List[float] = []
    content_type_counts: Dict[str, int] = {}
    artifact_type_counts: Dict[str, int] = {}

    for item in items:
        artifact = _artifact(item)
        content_type = _content_type(item, artifact)
        artifact_type = _artifact_type(artifact, content_type)
        content_type_counts[content_type] = content_type_counts.get(content_type, 0) + 1

        if artifact:
            artifact_count += 1
            artifact_type_counts[artifact_type] = artifact_type_counts.get(artifact_type, 0) + 1

        is_structured = content_type in STRUCTURED_EVIDENCE_TYPES or artifact_type in STRUCTURED_EVIDENCE_TYPES
        if is_structured:
            structured_count += 1
            if artifact:
                structured_with_artifact_count += 1

        if content_type == "table" or artifact_type == "table":
            table_count += 1
            if not artifact or not _has_table_structure(artifact):
                table_missing_structure_count += 1
            sources = artifact.get("sources") if artifact else None
            if not isinstance(sources, list) or not sources:
                table_missing_source_count += 1

        if content_type in {"image_ocr", "ocr"} or artifact_type in {"image_ocr", "ocr"}:
            ocr_count += 1
            images = artifact.get("images") if artifact else None
            images = images if isinstance(images, list) else []
            if not images:
                ocr_missing_source_count += 1
            ocr_low_confidence_source_count += sum(
                1 for image in images if isinstance(image, dict) and image.get("low_confidence") is True
            )
            ocr_confidence_values.extend(_ocr_confidences(images))

    artifact_coverage = round(artifact_count / evidence_count, 4) if evidence_count else None
    structured_artifact_coverage = (
        round(structured_with_artifact_count / structured_count, 4) if structured_count else None
    )
    ocr_avg_confidence = (
        round(sum(ocr_confidence_values) / len(ocr_confidence_values), 4)
        if ocr_confidence_values
        else None
    )

    warnings: List[str] = []
    recommendations: List[str] = []
    missing_structured_artifacts = structured_count - structured_with_artifact_count
    if missing_structured_artifacts:
        warnings.append(f"{missing_structured_artifacts} 条结构化证据缺少 artifact 预览")
        recommendations.append("重新解析或重建索引，确保表格、OCR、公式、代码证据保留结构化 artifact")
    if table_missing_structure_count:
        warnings.append(f"{table_missing_structure_count} 条表格证据缺少表头/样例行")
        recommendations.append("检查表格解析结果是否写入 headers、rows 或 markdown")
    if table_missing_source_count:
        warnings.append(f"{table_missing_source_count} 条表格证据缺少页码或表格来源")
        recommendations.append("补齐表格 artifact.sources，便于从答案定位到原文表格")
    if ocr_missing_source_count:
        warnings.append(f"{ocr_missing_source_count} 条 OCR 证据缺少图片来源")
        recommendations.append("补齐 OCR artifact.images，保留页码、图片序号、置信度和预览文本")
    if ocr_low_confidence_source_count:
        warnings.append(f"{ocr_low_confidence_source_count} 个 OCR 图片来源置信度偏低")
        recommendations.append("低置信 OCR 证据需要人工复核或提高图片解析质量")

    if evidence_count == 0:
        status = "no_evidence"
        risk_level = "high"
    elif warnings:
        status = "warn"
        risk_level = "high" if table_missing_structure_count or ocr_missing_source_count else "medium"
    else:
        status = "pass"
        risk_level = "low"

    return {
        "status": status,
        "risk_level": risk_level,
        "evidence_count": evidence_count,
        "artifact_count": artifact_count,
        "artifact_coverage": artifact_coverage,
        "structured_evidence_count": structured_count,
        "structured_artifact_count": structured_with_artifact_count,
        "structured_artifact_coverage": structured_artifact_coverage,
        "table_count": table_count,
        "table_missing_structure_count": table_missing_structure_count,
        "table_missing_source_count": table_missing_source_count,
        "ocr_count": ocr_count,
        "ocr_missing_source_count": ocr_missing_source_count,
        "ocr_low_confidence_source_count": ocr_low_confidence_source_count,
        "ocr_avg_confidence": ocr_avg_confidence,
        "content_type_counts": content_type_counts,
        "artifact_type_counts": artifact_type_counts,
        "warnings": warnings,
        "recommendations": recommendations,
    }
