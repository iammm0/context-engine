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


def _source_locator(item: EvidenceItem | Dict[str, Any]) -> Optional[Dict[str, Any]]:
    metadata = _metadata(item)
    locator = metadata.get("source_locator")
    return locator if isinstance(locator, dict) else None


def _source_locator_anchor_count(locator: Optional[Dict[str, Any]]) -> int:
    if not isinstance(locator, dict):
        return 0
    anchors = locator.get("anchors")
    anchor_list_count = len(anchors) if isinstance(anchors, list) else 0
    anchor_count = locator.get("anchor_count")
    if isinstance(anchor_count, int):
        return max(anchor_count, anchor_list_count, 0)
    return anchor_list_count


def _source_locator_has_anchor(locator: Optional[Dict[str, Any]]) -> bool:
    return _source_locator_anchor_count(locator) > 0


def _source_locator_has_bbox(locator: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(locator, dict):
        return False
    if locator.get("has_bbox"):
        return True
    anchors = locator.get("anchors") if isinstance(locator.get("anchors"), list) else []
    return any(isinstance(anchor, dict) and anchor.get("bbox") is not None for anchor in anchors)


def _source_locator_has_table_source(locator: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(locator, dict):
        return False
    if locator.get("has_table_source"):
        return True
    anchors = locator.get("anchors") if isinstance(locator.get("anchors"), list) else []
    return any(isinstance(anchor, dict) and anchor.get("type") == "table" for anchor in anchors)


def _source_locator_has_image_source(locator: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(locator, dict):
        return False
    if locator.get("has_image_source"):
        return True
    anchors = locator.get("anchors") if isinstance(locator.get("anchors"), list) else []
    return any(isinstance(anchor, dict) and anchor.get("type") == "image" for anchor in anchors)


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


def build_evidence_item_artifact_diagnostics(item: EvidenceItem | Dict[str, Any]) -> Dict[str, Any]:
    """Diagnose artifact completeness for one retrieved evidence item."""
    artifact = _artifact(item)
    content_type = _content_type(item, artifact)
    artifact_type = _artifact_type(artifact, content_type)
    is_structured = content_type in STRUCTURED_EVIDENCE_TYPES or artifact_type in STRUCTURED_EVIDENCE_TYPES

    warnings: List[str] = []
    recommendations: List[str] = []
    table_missing_structure = False
    table_missing_source = False
    ocr_missing_source = False
    ocr_low_confidence_source_count = 0
    ocr_avg_confidence = None

    if is_structured and not artifact:
        warnings.append("结构化证据缺少 artifact 预览")
        recommendations.append("重新解析或重建索引，确保结构化证据保留 artifact")

    if content_type == "table" or artifact_type == "table":
        table_missing_structure = not artifact or not _has_table_structure(artifact)
        sources = artifact.get("sources") if artifact else None
        table_missing_source = not isinstance(sources, list) or not sources
        if table_missing_structure:
            warnings.append("表格证据缺少表头、样例行或 Markdown 预览")
            recommendations.append("检查表格 artifact 是否写入 headers、rows 或 markdown")
        if table_missing_source:
            warnings.append("表格证据缺少页码或表格来源")
            recommendations.append("补齐表格 artifact.sources，便于定位原文表格")

    if content_type in {"image_ocr", "ocr"} or artifact_type in {"image_ocr", "ocr"}:
        images = artifact.get("images") if artifact else None
        images = images if isinstance(images, list) else []
        ocr_missing_source = not images
        if ocr_missing_source:
            warnings.append("OCR 证据缺少图片来源")
            recommendations.append("补齐 OCR artifact.images，保留页码、图片序号和置信度")
        ocr_low_confidence_source_count = sum(
            1 for image in images if isinstance(image, dict) and image.get("low_confidence") is True
        )
        confidence_values = _ocr_confidences(images)
        if confidence_values:
            ocr_avg_confidence = round(sum(confidence_values) / len(confidence_values), 4)
        if ocr_low_confidence_source_count:
            warnings.append(f"{ocr_low_confidence_source_count} 个 OCR 图片来源置信度偏低")
            recommendations.append("低置信 OCR 证据需要人工复核或提高图片解析质量")

    if not is_structured:
        status = "not_structured"
        risk_level = "low"
    elif warnings:
        status = "warn"
        risk_level = "high" if table_missing_structure or ocr_missing_source else "medium"
    else:
        status = "pass"
        risk_level = "low"

    return {
        "status": status,
        "risk_level": risk_level,
        "structured": is_structured,
        "content_type": content_type,
        "artifact_type": artifact_type,
        "has_artifact": bool(artifact),
        "table_missing_structure": table_missing_structure,
        "table_missing_source": table_missing_source,
        "ocr_missing_source": ocr_missing_source,
        "ocr_low_confidence_source_count": ocr_low_confidence_source_count,
        "ocr_avg_confidence": ocr_avg_confidence,
        "warnings": warnings,
        "recommendations": recommendations,
    }


def annotate_evidence_artifact_quality(evidence: Iterable[EvidenceItem]) -> None:
    """Attach per-item artifact diagnostics to structured evidence metadata."""
    for item in evidence:
        if not item:
            continue
        diagnostics = build_evidence_item_artifact_diagnostics(item)
        if not diagnostics.get("structured"):
            continue
        item.metadata = dict(item.metadata or {})
        item.metadata["artifact_quality"] = diagnostics


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
    source_locator_count = 0
    structured_source_locator_count = 0
    missing_source_locator_count = 0
    structured_missing_source_locator_count = 0
    bbox_source_locator_count = 0
    table_source_locator_count = 0
    ocr_source_locator_count = 0
    source_anchor_count = 0
    content_type_counts: Dict[str, int] = {}
    artifact_type_counts: Dict[str, int] = {}

    for item in items:
        artifact = _artifact(item)
        content_type = _content_type(item, artifact)
        artifact_type = _artifact_type(artifact, content_type)
        locator = _source_locator(item)
        has_source_locator = _source_locator_has_anchor(locator)
        content_type_counts[content_type] = content_type_counts.get(content_type, 0) + 1

        if artifact:
            artifact_count += 1
            artifact_type_counts[artifact_type] = artifact_type_counts.get(artifact_type, 0) + 1

        is_structured = content_type in STRUCTURED_EVIDENCE_TYPES or artifact_type in STRUCTURED_EVIDENCE_TYPES
        if has_source_locator:
            source_locator_count += 1
            source_anchor_count += _source_locator_anchor_count(locator)
            if _source_locator_has_bbox(locator):
                bbox_source_locator_count += 1
            if _source_locator_has_table_source(locator):
                table_source_locator_count += 1
            if _source_locator_has_image_source(locator):
                ocr_source_locator_count += 1
        else:
            missing_source_locator_count += 1

        if is_structured:
            structured_count += 1
            if artifact:
                structured_with_artifact_count += 1
            if has_source_locator:
                structured_source_locator_count += 1
            else:
                structured_missing_source_locator_count += 1

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
    source_locator_coverage = round(source_locator_count / evidence_count, 4) if evidence_count else None
    structured_source_locator_coverage = (
        round(structured_source_locator_count / structured_count, 4) if structured_count else None
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
    if structured_missing_source_locator_count:
        warnings.append(f"{structured_missing_source_locator_count} 条结构化证据缺少统一来源定位")
        recommendations.append("重新解析或重建索引，确保 source_locator 保留页码、字符范围、表格/OCR来源和 bbox")
    elif missing_source_locator_count:
        warnings.append(f"{missing_source_locator_count} 条证据缺少统一来源定位")
        recommendations.append("重建索引，确保检索证据携带 source_locator，便于答案引用回到原文位置")

    if evidence_count == 0:
        status = "no_evidence"
        risk_level = "high"
    elif warnings:
        status = "warn"
        risk_level = (
            "high"
            if table_missing_structure_count or ocr_missing_source_count or structured_missing_source_locator_count
            else "medium"
        )
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
        "source_locator_count": source_locator_count,
        "source_locator_coverage": source_locator_coverage,
        "structured_source_locator_count": structured_source_locator_count,
        "structured_source_locator_coverage": structured_source_locator_coverage,
        "missing_source_locator_count": missing_source_locator_count,
        "structured_missing_source_locator_count": structured_missing_source_locator_count,
        "bbox_source_locator_count": bbox_source_locator_count,
        "table_source_locator_count": table_source_locator_count,
        "ocr_source_locator_count": ocr_source_locator_count,
        "source_anchor_count": source_anchor_count,
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
