"""Chunk metadata helpers for ingestion, preview, and source citation."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from utils.evidence_quality import build_evidence_item_artifact_diagnostics


_WS_RE = re.compile(r"\s+")
_TABLE_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
_FORMULA_RE = re.compile(
    r"\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\begin\{(?:equation|align|matrix)\}",
    re.IGNORECASE,
)
_CODE_RE = re.compile(r"```|^\s{4,}(?:def|class|function|const|let|var)\b", re.MULTILINE)
_HEADING_PATTERNS = [
    re.compile(r"^#{1,6}\s+(.+?)\s*$"),
    re.compile(r"^(第[一二三四五六七八九十0-9]+[章节节])\s*(.+?)\s*$"),
    re.compile(r"^(\d+(?:\.\d+){0,4})\s+(.+?)\s*$"),
    re.compile(r"^([一二三四五六七八九十]+、|\（[一二三四五六七八九十]+\）|\d+\))\s*(.+?)\s*$"),
]
_HEAVY_METADATA_KEYS = {"pages", "tables", "formulas", "code_blocks"}
_MARKDOWN_TABLE_LINE_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_MARKDOWN_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_OCR_MARKER_RE = re.compile(r"\[图片文字(?:\s+page=(?P<page>\d+))?(?:\s+image=(?P<image>\d+))?\]")


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        parsed = float(value)
        if parsed != parsed:
            return None
        return parsed
    except Exception:
        return None


def _normalize_confidence(value: Any) -> Optional[float]:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    if parsed > 1:
        parsed = parsed / 100.0
    return max(0.0, min(1.0, parsed))


def _first_int(*values: Any) -> Optional[int]:
    for value in values:
        parsed = _safe_int(value)
        if parsed is not None:
            return parsed
    return None


def _clean_preview(text: str, max_chars: int = 240) -> str:
    normalized = _WS_RE.sub(" ", (text or "").strip())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "..."


def _list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _summarize_ocr_quality(metadata: Dict[str, Any]) -> Dict[str, Any]:
    image_ocr = metadata.get("image_ocr") if isinstance(metadata.get("image_ocr"), dict) else {}
    images = image_ocr.get("images") if isinstance(image_ocr.get("images"), list) else []
    image_count = _safe_int(image_ocr.get("image_count")) or len(images)
    recognized_images = 0
    empty_images = 0
    low_confidence_images = 0
    confidences: List[float] = []
    observed_images = 0

    for image in images:
        if not isinstance(image, dict):
            continue
        observed_images += 1
        text_length = _safe_int(image.get("text_length"))
        if text_length is None and isinstance(image.get("text"), str):
            text_length = len(image.get("text") or "")
        line_count = _safe_int(image.get("line_count")) or 0
        has_text = (text_length or 0) > 0 or line_count > 0
        confidence = _normalize_confidence(image.get("confidence"))

        if has_text:
            recognized_images += 1
            if confidence is not None:
                confidences.append(confidence)
                if confidence < 0.65:
                    low_confidence_images += 1
        else:
            empty_images += 1

    if image_count > observed_images:
        empty_images += image_count - observed_images

    ocr_image_coverage = None
    if image_count:
        ocr_image_coverage = max(0.0, min(1.0, recognized_images / max(float(image_count), 1.0)))

    return {
        "ocr_recognized_images": recognized_images,
        "ocr_empty_images": empty_images,
        "ocr_low_confidence_images": low_confidence_images,
        "ocr_avg_confidence": (sum(confidences) / len(confidences)) if confidences else None,
        "ocr_image_coverage": ocr_image_coverage,
    }


def _chunk_token_count(chunk: Dict[str, Any]) -> Optional[int]:
    metadata = chunk.get("metadata") or {}
    for value in (metadata.get("token_count"), chunk.get("token_count")):
        parsed = _safe_int(value)
        if parsed is not None:
            return max(0, parsed)
    return None


def _chunk_has_anchor(chunk: Dict[str, Any]) -> bool:
    metadata = chunk.get("metadata") or {}
    visual = metadata.get("visual") if isinstance(metadata.get("visual"), dict) else {}
    for source in (metadata, visual):
        if source.get("page") is not None or source.get("page_start") is not None or source.get("page_end") is not None:
            return True
        if source.get("char_start") is not None and source.get("char_end") is not None:
            return True
    artifact = metadata.get("artifact") if isinstance(metadata.get("artifact"), dict) else visual.get("artifact")
    images = artifact.get("images") if isinstance(artifact, dict) and isinstance(artifact.get("images"), list) else []
    return any(
        isinstance(image, dict) and (image.get("page") is not None or image.get("target") or image.get("image_index") is not None)
        for image in images
    )


def _summarize_chunk_quality(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    token_counts = [count for chunk in chunks if (count := _chunk_token_count(chunk)) is not None]
    anchored_count = sum(1 for chunk in chunks if _chunk_has_anchor(chunk))
    summary: Dict[str, Any] = {
        "chunk_anchor_count": anchored_count,
        "chunk_missing_anchor_count": max(len(chunks) - anchored_count, 0),
        "chunk_anchor_coverage": (anchored_count / len(chunks)) if chunks else None,
    }
    if token_counts:
        summary.update(
            {
                "chunk_token_min": min(token_counts),
                "chunk_token_max": max(token_counts),
                "chunk_token_avg": round(sum(token_counts) / len(token_counts), 1),
                "chunk_short_count": sum(1 for count in token_counts if count < 40),
                "chunk_large_count": sum(1 for count in token_counts if count > 1200),
            }
        )
    return summary


def _summarize_artifact_quality(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    expected_types = {"table", "image_ocr", "ocr", "formula", "code"}
    expected_count = 0
    present_count = 0
    missing_count = 0
    issue_count = 0
    table_issue_count = 0
    table_missing_structure_count = 0
    table_missing_source_count = 0
    ocr_issue_count = 0
    ocr_missing_source_count = 0
    low_confidence_ocr_source_count = 0

    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        content_type = str(metadata.get("content_type") or "text").lower()
        if content_type not in expected_types:
            continue
        expected_count += 1
        artifact = metadata.get("artifact")
        artifact = artifact if isinstance(artifact, dict) else None
        diagnostics = build_evidence_item_artifact_diagnostics(
            {"metadata": {"content_type": content_type, "artifact": artifact}}
        )

        if not artifact:
            missing_count += 1
        else:
            present_count += 1

        if diagnostics.get("status") in {"warn", "fail"}:
            issue_count += 1

        artifact_type = str((artifact or {}).get("type") or diagnostics.get("artifact_type") or "").lower()
        if content_type == "table" or artifact_type == "table":
            if diagnostics.get("status") in {"warn", "fail"}:
                table_issue_count += 1
            if diagnostics.get("table_missing_structure"):
                table_missing_structure_count += 1
            if diagnostics.get("table_missing_source"):
                table_missing_source_count += 1
        if content_type in {"image_ocr", "ocr"} or artifact_type in {"image_ocr", "ocr"}:
            if diagnostics.get("status") in {"warn", "fail"}:
                ocr_issue_count += 1
            if diagnostics.get("ocr_missing_source"):
                ocr_missing_source_count += 1
            low_confidence_ocr_source_count += int(diagnostics.get("ocr_low_confidence_source_count") or 0)

    return {
        "artifact_expected_count": expected_count,
        "artifact_present_count": present_count,
        "artifact_missing_count": missing_count,
        "artifact_issue_count": issue_count,
        "artifact_preview_coverage": (present_count / expected_count) if expected_count else None,
        "table_artifact_issue_count": table_issue_count,
        "table_artifact_missing_structure_count": table_missing_structure_count,
        "table_artifact_missing_source_count": table_missing_source_count,
        "ocr_artifact_issue_count": ocr_issue_count,
        "ocr_artifact_missing_source_count": ocr_missing_source_count,
        "ocr_artifact_low_confidence_source_count": low_confidence_ocr_source_count,
    }


def summarize_parse_metadata(metadata: Dict[str, Any], document_text: str = "") -> Dict[str, Any]:
    """Build a compact document-level parse summary safe to repeat on chunks."""
    image_ocr = metadata.get("image_ocr") if isinstance(metadata.get("image_ocr"), dict) else {}
    page_count = _safe_int(metadata.get("page_count")) or _safe_int(metadata.get("pages"))
    if page_count is None and isinstance(metadata.get("pages"), list):
        page_count = len(metadata["pages"])

    return {
        **_summarize_ocr_quality(metadata),
        "parser_type": metadata.get("parser_type"),
        "extraction_method": metadata.get("extraction_method"),
        "page_count": page_count,
        "extracted_pages": _safe_int(metadata.get("extracted_pages")),
        "table_count": _list_count(metadata.get("tables")),
        "formula_count": _list_count(metadata.get("formulas")),
        "image_count": _safe_int(image_ocr.get("image_count")) or 0,
        "ocr_text_length": _safe_int(image_ocr.get("ocr_text_length")) or 0,
        "text_length": len(document_text or ""),
    }


def build_parse_quality_summary(
    metadata: Dict[str, Any],
    document_text: str = "",
    chunks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a document-level parse quality summary for UI and diagnostics."""
    summary = summarize_parse_metadata(metadata, document_text)
    chunks = chunks or []

    content_type_counts: Dict[str, int] = {}
    for chunk in chunks:
        chunk_meta = chunk.get("metadata") or {}
        content_type = str(chunk_meta.get("content_type") or "text")
        content_type_counts[content_type] = content_type_counts.get(content_type, 0) + 1
    chunk_quality = _summarize_chunk_quality(chunks)
    artifact_quality = _summarize_artifact_quality(chunks)

    page_count = summary.get("page_count") or 0
    extracted_pages = summary.get("extracted_pages")
    if extracted_pages is None and page_count and len(document_text or "") > 0:
        extracted_pages = page_count

    page_coverage = None
    if page_count and extracted_pages is not None:
        page_coverage = max(0.0, min(1.0, float(extracted_pages) / max(float(page_count), 1.0)))

    warnings: List[str] = []
    checks: List[Dict[str, Any]] = []
    score = 100

    def add_check(
        check_id: str,
        label: str,
        status: str,
        severity: str,
        message: str,
        action: str = "",
        *,
        content_type_filter: str = "",
        feature_filter: str = "",
        filter_label: str = "",
    ) -> None:
        item = {
            "id": check_id,
            "label": label,
            "status": status,
            "severity": severity,
            "message": message,
        }
        if action:
            item["action"] = action
        if content_type_filter:
            item["content_type_filter"] = content_type_filter
        if feature_filter:
            item["feature_filter"] = feature_filter
        if filter_label:
            item["filter_label"] = filter_label
        checks.append(item)

    text_length = int(summary.get("text_length") or 0)
    if text_length == 0:
        score -= 60
        add_check(
            "text_extraction",
            "正文文本",
            "fail",
            "critical",
            "未提取到正文文本",
            "检查解析器选择、扫描件 OCR 开关和原始文件是否损坏。",
        )
        warnings.append("未提取到正文文本")
    elif text_length < 200:
        score -= 15
        add_check(
            "text_extraction",
            "正文文本",
            "warn",
            "warning",
            "正文文本较短，可能存在解析不完整",
            "抽查文档预览，必要时切换解析器或启用 OCR。",
        )
        warnings.append("正文文本较短，可能存在解析不完整")
    else:
        add_check("text_extraction", "正文文本", "pass", "info", f"已提取 {text_length} 字正文")

    if page_coverage is not None and page_coverage < 0.9:
        penalty = int((1.0 - page_coverage) * 35)
        score -= max(5, penalty)
        add_check(
            "page_coverage",
            "页面覆盖",
            "warn",
            "warning",
            f"页面文本覆盖率偏低：{page_coverage:.0%}",
            "检查缺页是否为扫描页、图片页或受保护内容。",
        )
        warnings.append(f"页面文本覆盖率偏低：{page_coverage:.0%}")
    elif page_coverage is not None:
        add_check("page_coverage", "页面覆盖", "pass", "info", f"页面文本覆盖率 {page_coverage:.0%}")

    image_count = int(summary.get("image_count") or 0)
    ocr_text_length = int(summary.get("ocr_text_length") or 0)
    ocr_recognized_images = int(summary.get("ocr_recognized_images") or 0)
    ocr_empty_images = int(summary.get("ocr_empty_images") or 0)
    ocr_low_confidence_images = int(summary.get("ocr_low_confidence_images") or 0)
    ocr_avg_confidence = summary.get("ocr_avg_confidence")
    ocr_image_coverage = summary.get("ocr_image_coverage")
    if image_count > 0 and ocr_text_length == 0:
        score -= 10
        add_check(
            "image_ocr",
            "图片 OCR",
            "warn",
            "warning",
            "检测到图片但未产生 OCR 文本",
            "确认 OCR 模块可用，并抽查图片是否包含可识别文字。",
        )
        warnings.append("检测到图片但未产生 OCR 文本")
    elif image_count > 0:
        if isinstance(ocr_image_coverage, float) and ocr_image_coverage < 0.8:
            score -= 8
            add_check(
                "image_ocr",
                "图片 OCR",
                "warn",
                "warning",
                f"图片 OCR 覆盖率偏低：{ocr_image_coverage:.0%}，{ocr_empty_images} 张图片未识别到文字",
                "抽查未识别图片，必要时提升图片清晰度、开启高精度 OCR 或重新解析。",
            )
            warnings.append(f"图片 OCR 覆盖率偏低：{ocr_image_coverage:.0%}")
        else:
            message = f"检测到 {image_count} 张图片，OCR 文本 {ocr_text_length} 字"
            if isinstance(ocr_image_coverage, float):
                message = f"检测到 {image_count} 张图片，识别 {ocr_recognized_images} 张，OCR 文本 {ocr_text_length} 字"
            add_check("image_ocr", "图片 OCR", "pass", "info", message)

        if isinstance(ocr_avg_confidence, float):
            if ocr_avg_confidence < 0.6:
                score -= 8
                add_check(
                    "ocr_confidence",
                    "OCR 置信度",
                    "warn",
                    "warning",
                    f"OCR 平均置信度偏低：{ocr_avg_confidence:.0%}",
                    "复核 OCR 文本，必要时更换 OCR 引擎或提高扫描分辨率。",
                )
                warnings.append(f"OCR 平均置信度偏低：{ocr_avg_confidence:.0%}")
            elif ocr_low_confidence_images > 0:
                score -= min(6, max(2, ocr_low_confidence_images * 2))
                add_check(
                    "ocr_confidence",
                    "OCR 置信度",
                    "warn",
                    "warning",
                    f"{ocr_low_confidence_images} 张图片 OCR 置信度偏低，平均置信度 {ocr_avg_confidence:.0%}",
                    "优先复核低置信度图片对应的证据引用。",
                )
                warnings.append(f"{ocr_low_confidence_images} 张图片 OCR 置信度偏低")
            else:
                add_check("ocr_confidence", "OCR 置信度", "pass", "info", f"平均置信度 {ocr_avg_confidence:.0%}")

    if chunks and not content_type_counts:
        score -= 10
        add_check(
            "chunk_types",
            "切块类型",
            "fail",
            "critical",
            "未识别到有效切块类型",
            "检查切块器是否返回 metadata.content_type。",
        )
        warnings.append("未识别到有效切块类型")
    elif chunks:
        add_check("chunk_types", "切块类型", "pass", "info", f"识别到 {len(content_type_counts)} 类切块")

    if chunks:
        anchor_coverage = chunk_quality.get("chunk_anchor_coverage")
        missing_anchor_count = int(chunk_quality.get("chunk_missing_anchor_count") or 0)
        if isinstance(anchor_coverage, float) and anchor_coverage < 0.8:
            score -= 6
            add_check(
                "chunk_anchors",
                "切块定位",
                "warn",
                "warning",
                f"切块定位覆盖率偏低：{anchor_coverage:.0%}，{missing_anchor_count} 个 chunk 缺少页码、字符范围或图片来源",
                "重新解析并保留页码/字符偏移，或检查切块器是否丢失 metadata。",
                feature_filter="missing_anchor",
                filter_label="查看缺定位切块",
            )
            warnings.append(f"切块定位覆盖率偏低：{anchor_coverage:.0%}")
        else:
            message = "切块均带有可视化定位"
            if isinstance(anchor_coverage, float):
                message = f"切块定位覆盖率 {anchor_coverage:.0%}"
            add_check("chunk_anchors", "切块定位", "pass", "info", message)

        token_counts_seen = chunk_quality.get("chunk_token_avg") is not None
        if token_counts_seen:
            short_count = int(chunk_quality.get("chunk_short_count") or 0)
            large_count = int(chunk_quality.get("chunk_large_count") or 0)
            problem_count = short_count + large_count
            problem_ratio = problem_count / max(len(chunks), 1)
            if problem_ratio >= 0.3:
                score -= 6
                add_check(
                    "chunk_size",
                    "切块大小",
                    "warn",
                    "warning",
                    f"切块大小分布不均：{short_count} 个过短，{large_count} 个过长，平均 {chunk_quality.get('chunk_token_avg')} tokens",
                    "调整 chunk_size/chunk_overlap，避免过碎或超长 chunk 影响召回和引用。",
                    feature_filter="size_issue",
                    filter_label="查看尺寸异常切块",
                )
                warnings.append("切块大小分布不均")
            else:
                add_check(
                    "chunk_size",
                    "切块大小",
                    "pass",
                    "info",
                    f"平均 {chunk_quality.get('chunk_token_avg')} tokens，范围 {chunk_quality.get('chunk_token_min')}-{chunk_quality.get('chunk_token_max')}",
                )

        artifact_expected_count = int(artifact_quality.get("artifact_expected_count") or 0)
        artifact_missing_count = int(artifact_quality.get("artifact_missing_count") or 0)
        artifact_issue_count = int(artifact_quality.get("artifact_issue_count") or 0)
        table_artifact_missing_structure_count = int(artifact_quality.get("table_artifact_missing_structure_count") or 0)
        table_artifact_missing_source_count = int(artifact_quality.get("table_artifact_missing_source_count") or 0)
        ocr_artifact_missing_source_count = int(artifact_quality.get("ocr_artifact_missing_source_count") or 0)
        ocr_artifact_low_confidence_source_count = int(artifact_quality.get("ocr_artifact_low_confidence_source_count") or 0)
        artifact_preview_coverage = artifact_quality.get("artifact_preview_coverage")
        if artifact_expected_count:
            if artifact_issue_count:
                score -= min(10, max(3, artifact_issue_count * 2))
                issues = []
                if artifact_missing_count:
                    issues.append(f"{artifact_missing_count} 个结构化 chunk 缺少 artifact")
                if table_artifact_missing_structure_count:
                    issues.append(f"{table_artifact_missing_structure_count} 个表格 artifact 缺少表头/行或 Markdown")
                if table_artifact_missing_source_count:
                    issues.append(f"{table_artifact_missing_source_count} 个表格 artifact 缺少页码或来源")
                if ocr_artifact_missing_source_count:
                    issues.append(f"{ocr_artifact_missing_source_count} 个 OCR artifact 缺少图片来源")
                if ocr_artifact_low_confidence_source_count:
                    issues.append(f"{ocr_artifact_low_confidence_source_count} 个 OCR 图片来源置信度偏低")
                coverage_text = (
                    f"，覆盖率 {artifact_preview_coverage:.0%}"
                    if isinstance(artifact_preview_coverage, float)
                    else ""
                )
                add_check(
                    "chunk_artifacts",
                    "结构化预览",
                    "warn",
                    "warning",
                    f"{artifact_issue_count} 个结构化 chunk 存在 artifact 问题{coverage_text}：" + "；".join(issues),
                    "复核结构化 artifact 是否携带表格结构、页码来源、图片来源和 OCR 文本预览。",
                    feature_filter="artifact_issue",
                    filter_label="查看问题切块",
                )
                if table_artifact_missing_structure_count:
                    add_check(
                        "table_artifact_structure",
                        "表格结构",
                        "warn",
                        "warning",
                        f"{table_artifact_missing_structure_count} 个表格 artifact 缺少表头、行数据或 Markdown 预览",
                        "复核表格解析结果是否保留列名和单元格结构，必要时切换表格解析策略后重建索引。",
                        feature_filter="table_missing_structure",
                        filter_label="查看缺结构表格",
                    )
                if table_artifact_missing_source_count:
                    add_check(
                        "table_artifact_source",
                        "表格来源",
                        "warn",
                        "warning",
                        f"{table_artifact_missing_source_count} 个表格 artifact 缺少页码或来源定位",
                        "重新解析并保留表格页码、表格索引或 bbox，避免答案引用无法回到原文位置。",
                        feature_filter="table_missing_source",
                        filter_label="查看缺来源表格",
                    )
                if ocr_artifact_missing_source_count:
                    add_check(
                        "ocr_artifact_source",
                        "OCR来源",
                        "warn",
                        "warning",
                        f"{ocr_artifact_missing_source_count} 个 OCR artifact 缺少图片来源",
                        "复核 OCR 输出是否携带图片索引、页码或嵌入图片路径，避免图片文字证据无法定位。",
                        feature_filter="ocr_missing_source",
                        filter_label="查看缺来源OCR",
                    )
                if ocr_artifact_low_confidence_source_count:
                    add_check(
                        "ocr_artifact_confidence",
                        "OCR置信度",
                        "warn",
                        "warning",
                        f"{ocr_artifact_low_confidence_source_count} 个 OCR 图片来源置信度偏低",
                        "优先复核低置信 OCR 来源，必要时提升图片清晰度或更换 OCR 引擎后重新解析。",
                        feature_filter="ocr_low_confidence",
                        filter_label="查看低置信OCR",
                    )
                warnings.append("结构化 artifact 信息不完整")
            else:
                add_check(
                    "chunk_artifacts",
                    "结构化预览",
                    "pass",
                    "info",
                    f"结构化 artifact 覆盖率 {artifact_preview_coverage:.0%}",
                )

    table_count = int(summary.get("table_count") or 0)
    formula_count = int(summary.get("formula_count") or 0)
    if table_count > 0 and int(content_type_counts.get("table") or 0) == 0:
        score -= 8
        add_check(
            "table_chunks",
            "表格切块",
            "warn",
            "warning",
            "解析到表格，但切块中未标记表格块",
            "检查表格解析结果是否被合并到正文，或调整切块策略保留表格边界。",
        )
        warnings.append("解析到表格，但切块中未标记表格块")
    elif table_count > 0:
        add_check("table_chunks", "表格切块", "pass", "info", f"表格解析 {table_count} 个，表格切块 {content_type_counts.get('table', 0)} 个")

    if formula_count > 0 and int(content_type_counts.get("formula") or 0) == 0:
        score -= 5
        add_check(
            "formula_chunks",
            "公式切块",
            "warn",
            "warning",
            "解析到公式，但切块中未标记公式块",
            "检查公式分析器输出和切块器的公式类型识别。",
        )
        warnings.append("解析到公式，但切块中未标记公式块")
    elif formula_count > 0:
        add_check("formula_chunks", "公式切块", "pass", "info", f"公式解析 {formula_count} 个")

    score = max(0, min(100, score))
    recommendations = [
        str(item["action"])
        for item in checks
        if item.get("action") and item.get("status") in {"warn", "fail"}
    ]
    has_critical = any(item.get("status") == "fail" or item.get("severity") == "critical" for item in checks)
    if score < 60 or has_critical:
        risk_level = "high"
    elif score < 85 or warnings:
        risk_level = "medium"
    else:
        risk_level = "low"
    return {
        **summary,
        **chunk_quality,
        **artifact_quality,
        "chunk_count": len(chunks),
        "content_type_counts": content_type_counts,
        "page_coverage": page_coverage,
        "quality_score": score,
        "risk_level": risk_level,
        "quality_checks": checks,
        "recommendations": recommendations,
        "warnings": warnings,
    }


def _build_page_spans(metadata: Dict[str, Any]) -> List[Tuple[int, int, int]]:
    pages = metadata.get("pages")
    if not isinstance(pages, list):
        return []

    spans: List[Tuple[int, int, int]] = []
    cursor = 0
    for index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            continue
        page_text = str(page.get("text") or "")
        page_no = _safe_int(page.get("page") or page.get("page_number")) or index
        start = cursor
        end = start + len(page_text)
        if end > start:
            spans.append((page_no, start, end))
        # PDFParser joins pages with two newlines.
        cursor = end + 2
    return spans


def _find_text_span(document_text: str, chunk_text: str, cursor: int) -> Tuple[int, int]:
    if not document_text or not chunk_text:
        return cursor, cursor

    search_start = max(0, cursor - 200)
    pos = document_text.find(chunk_text, search_start)
    if pos < 0:
        needle = chunk_text[: min(len(chunk_text), 120)].strip()
        pos = document_text.find(needle, search_start) if needle else -1
    if pos < 0:
        pos = cursor
    return pos, pos + len(chunk_text)


def _page_range_for_span(
    start: Optional[int],
    end: Optional[int],
    page_spans: List[Tuple[int, int, int]],
) -> Tuple[Optional[int], Optional[int]]:
    if start is None or end is None or not page_spans:
        return None, None
    matched: List[int] = []
    for page_no, page_start, page_end in page_spans:
        if max(start, page_start) < min(end, page_end):
            matched.append(page_no)
    if not matched:
        return None, None
    return min(matched), max(matched)


def _infer_section_path(text: str, metadata: Dict[str, Any]) -> List[str]:
    section_path = metadata.get("section_path")
    if isinstance(section_path, list):
        return [str(item)[:200] for item in section_path if str(item).strip()][:8]
    if isinstance(section_path, str) and section_path.strip():
        return [section_path[:200]]

    detected: List[str] = []
    for line in (text or "").splitlines()[:8]:
        line = line.strip()
        if not line:
            continue
        for pattern in _HEADING_PATTERNS:
            match = pattern.match(line)
            if match:
                heading = (match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1)).strip()
                if heading and heading not in detected:
                    detected.append(heading[:200])
                break
    return detected[:4]


def _infer_features(text: str, metadata: Dict[str, Any]) -> Dict[str, bool]:
    content_type = str(metadata.get("content_type") or "").lower()
    has_table = content_type == "table" or "[表格]" in text or bool(_TABLE_RE.search(text))
    has_formula = content_type == "formula" or bool(_FORMULA_RE.search(text))
    has_code = content_type == "code" or bool(_CODE_RE.search(text))
    has_image_ocr = (
        content_type in {"image_ocr", "ocr"}
        or "[图片文字" in text
        or metadata.get("extraction_method") == "image_ocr"
        or bool(metadata.get("image_ocr"))
    )
    return {
        "has_table": has_table,
        "has_formula": has_formula,
        "has_code": has_code,
        "has_image_ocr": has_image_ocr,
    }


def _infer_content_type(text: str, metadata: Dict[str, Any]) -> str:
    existing = str(metadata.get("content_type") or "").strip().lower()
    if existing and existing not in {"auto", "unknown"}:
        return existing

    features = _infer_features(text, metadata)
    if features["has_table"]:
        return "table"
    if features["has_image_ocr"]:
        return "image_ocr"
    if features["has_formula"]:
        return "formula"
    if features["has_code"]:
        return "code"
    return "text"


def _compact_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Remove repeated heavy document-level payloads from per-chunk metadata."""
    return {key: value for key, value in metadata.items() if key not in _HEAVY_METADATA_KEYS}


def _strip_ocr_markers(text: str) -> str:
    return _OCR_MARKER_RE.sub("", text or "").strip()


def _ocr_image_lookup(metadata: Dict[str, Any]) -> Dict[Tuple[Optional[int], Optional[int]], Dict[str, Any]]:
    image_ocr = metadata.get("image_ocr") if isinstance(metadata.get("image_ocr"), dict) else {}
    images = image_ocr.get("images") if isinstance(image_ocr.get("images"), list) else []
    lookup: Dict[Tuple[Optional[int], Optional[int]], Dict[str, Any]] = {}
    for image in images:
        if not isinstance(image, dict):
            continue
        page = _safe_int(image.get("page"))
        image_index = _safe_int(image.get("image_index"))
        lookup[(page, image_index)] = image
    return lookup


def _ocr_text_preview(image: Dict[str, Any]) -> str:
    for key in ("text_preview", "ocr_text", "text"):
        value = image.get(key)
        if isinstance(value, str) and value.strip():
            return _clean_preview(value, max_chars=160)
    return ""


def _build_ocr_ref(page: Optional[int], image_index: Optional[int], image_meta: Dict[str, Any]) -> Dict[str, Any]:
    confidence = image_meta.get("confidence")
    normalized_confidence = _normalize_confidence(confidence)
    ref = {
        "page": page,
        "image_index": image_index,
        "confidence": confidence,
        "line_count": image_meta.get("line_count"),
        "text_length": image_meta.get("text_length"),
        "width": image_meta.get("width"),
        "height": image_meta.get("height"),
        "target": image_meta.get("target"),
        "bbox": image_meta.get("bbox"),
    }
    text_preview = _ocr_text_preview(image_meta)
    if text_preview:
        ref["text_preview"] = text_preview
    if normalized_confidence is not None:
        ref["low_confidence"] = normalized_confidence < 0.65
    return ref


def _extract_ocr_refs(text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    lookup = _ocr_image_lookup(metadata)
    refs: List[Dict[str, Any]] = []
    for match in _OCR_MARKER_RE.finditer(text or ""):
        page = _safe_int(match.group("page"))
        image_index = _safe_int(match.group("image"))
        image_meta = lookup.get((page, image_index), {})
        if page is None and image_index is None and not image_meta:
            continue
        refs.append(_build_ocr_ref(page, image_index, image_meta))

    if refs:
        return refs

    image_ocr = metadata.get("image_ocr") if isinstance(metadata.get("image_ocr"), dict) else {}
    images = image_ocr.get("images") if isinstance(image_ocr.get("images"), list) else []
    for image in images[:3]:
        if isinstance(image, dict):
            refs.append(_build_ocr_ref(_safe_int(image.get("page")), _safe_int(image.get("image_index")), image))
    return refs


def _extract_markdown_table(text: str, max_rows: int = 12, max_cols: int = 8) -> Optional[Dict[str, Any]]:
    rows: List[List[str]] = []
    table_lines: List[str] = []
    for line in (text or "").splitlines():
        if _MARKDOWN_TABLE_LINE_RE.match(line):
            table_lines.append(line.strip())
            if _MARKDOWN_TABLE_SEPARATOR_RE.match(line):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if cells:
                rows.append(cells[:max_cols])
        elif table_lines:
            break

    if not rows:
        return None

    headers = rows[0]
    body_rows = rows[1:max_rows]
    return {
        "type": "table",
        "markdown": "\n".join(table_lines[: max_rows + 1]),
        "headers": headers,
        "rows": body_rows,
        "row_count": max(len(rows) - 1, 0),
        "column_count": len(headers),
    }


def _clean_source_value(value: Any, max_chars: int = 200) -> str:
    return _clean_preview(str(value or ""), max_chars=max_chars)


def _compact_bbox(value: Any) -> Optional[Any]:
    if isinstance(value, dict):
        compact = {
            key: value.get(key)
            for key in ("x0", "y0", "x1", "y1", "left", "top", "right", "bottom", "width", "height")
            if value.get(key) is not None
        }
        return compact or None
    if isinstance(value, (list, tuple)) and value:
        return list(value[:8])
    return None


def _table_source_ref(table: Dict[str, Any], index: int) -> Dict[str, Any]:
    semantic = table.get("semantic") if isinstance(table.get("semantic"), dict) else {}
    semantic_row_count = _safe_int(semantic.get("row_count"))
    table_index = _first_int(table.get("table_index"), table.get("index"), table.get("table_id"), table.get("id"))
    ref: Dict[str, Any] = {
        "table_index": table_index if table_index is not None else index + 1,
    }
    page = _first_int(table.get("page"), table.get("page_number"), table.get("page_no"), table.get("page_start"))
    page_end = _first_int(table.get("page_end"))
    if page is not None:
        ref["page"] = page
    if page_end is not None and page_end != page:
        ref["page_end"] = page_end
    table_type = _clean_source_value(table.get("type"), max_chars=80)
    if table_type:
        ref["type"] = table_type
    for key in ("caption", "title", "name", "source", "target"):
        value = _clean_source_value(table.get(key))
        if value:
            ref[key] = value
    bbox = _compact_bbox(table.get("bbox") or table.get("bounding_box") or table.get("bounds"))
    if bbox:
        ref["bbox"] = bbox

    row_count = _first_int(table.get("row_count"), semantic_row_count)
    col_count = _first_int(table.get("column_count"), table.get("col_count"), semantic.get("col_count"))
    data = table.get("data")
    if row_count is None and isinstance(data, list) and data:
        row_count = max(len(data) - 1, 0)
    if col_count is None and isinstance(data, list) and data and isinstance(data[0], list):
        col_count = len(data[0])
    if row_count is not None:
        ref["row_count"] = max(row_count - 1, 0) if semantic_row_count is not None and row_count == semantic_row_count else max(row_count, 0)
    if col_count is not None:
        ref["column_count"] = max(col_count, 0)
    return ref


def _normalize_table_match_text(value: Any) -> str:
    return _WS_RE.sub(" ", str(value or "").strip()).lower()


def _table_matches_text(table: Dict[str, Any], text: str) -> bool:
    haystack = _normalize_table_match_text(text)
    if not haystack:
        return False
    candidates = [table.get("markdown"), table.get("raw")]
    data = table.get("data")
    if isinstance(data, list):
        flattened_rows = []
        for row in data:
            if isinstance(row, list):
                flattened_rows.append(" | ".join(str("" if cell is None else cell) for cell in row))
        if flattened_rows:
            candidates.append(" ".join(flattened_rows))
    for candidate in candidates:
        normalized = _normalize_table_match_text(candidate)
        if normalized and (normalized in haystack or haystack in normalized):
            return True
    return False


def _table_sources_from_metadata(metadata: Dict[str, Any], *, text: str = "", max_sources: int = 3) -> List[Dict[str, Any]]:
    tables = metadata.get("tables")
    if not isinstance(tables, list):
        return []
    matches: List[Dict[str, Any]] = []
    fallbacks: List[Dict[str, Any]] = []
    for index, table in enumerate(tables):
        if not isinstance(table, dict):
            continue
        ref = _table_source_ref(table, index)
        fallbacks.append(ref)
        if text and _table_matches_text(table, text):
            matches.append(ref)
    return (matches or fallbacks)[:max_sources]


def _with_table_sources(artifact: Optional[Dict[str, Any]], sources: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not artifact:
        return artifact
    if sources:
        artifact = dict(artifact)
        artifact["sources"] = sources[:3]
    return artifact


def _table_data_to_artifact(data: Any, *, markdown: str = "", max_rows: int = 12, max_cols: int = 8) -> Optional[Dict[str, Any]]:
    if not isinstance(data, list) or not data:
        return None
    rows = []
    for row in data:
        if isinstance(row, list):
            cells = [str("" if cell is None else cell).strip() for cell in row[:max_cols]]
            rows.append(cells)
    if not rows:
        return None
    headers = rows[0]
    body_rows = rows[1:max_rows]
    return {
        "type": "table",
        "markdown": markdown,
        "headers": headers,
        "rows": body_rows,
        "row_count": max(len(rows) - 1, 0),
        "column_count": len(headers),
    }


def _table_from_metadata(metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tables = metadata.get("tables")
    if not isinstance(tables, list):
        return None
    for index, table in enumerate(tables):
        if not isinstance(table, dict):
            continue
        sources = [_table_source_ref(table, index)]
        markdown = str(table.get("markdown") or table.get("raw") or "").strip()
        if markdown:
            parsed = _extract_markdown_table(markdown)
            if parsed:
                return _with_table_sources(parsed, sources)
        parsed = _table_data_to_artifact(table.get("data"), markdown=markdown)
        if parsed:
            return _with_table_sources(parsed, sources)
        semantic = table.get("semantic")
        if isinstance(semantic, dict):
            headers = [str(item or "").strip() for item in semantic.get("headers") or []]
            if headers:
                row_count = _safe_int(semantic.get("row_count")) or 0
                col_count = _safe_int(semantic.get("col_count")) or len(headers)
                return _with_table_sources(
                    {
                        "type": "table",
                        "markdown": markdown,
                        "headers": headers,
                        "rows": [],
                        "row_count": max(row_count - 1, 0),
                        "column_count": col_count,
                    },
                    sources,
                )
    return None


def _build_chunk_artifact(text: str, content_type: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a compact preview artifact for non-plain-text chunks."""
    normalized_type = (content_type or "text").lower()
    if normalized_type == "table" or bool(_TABLE_RE.search(text or "")):
        table = _extract_markdown_table(text)
        if table:
            return _with_table_sources(table, _table_sources_from_metadata(metadata, text=text))
        table = _table_from_metadata(metadata)
        if table:
            return table
        fallback = {
            "type": "table",
            "markdown": _clean_preview(text, max_chars=800),
            "headers": [],
            "rows": [],
            "row_count": None,
            "column_count": None,
        }
        return _with_table_sources(fallback, _table_sources_from_metadata(metadata, text=text))

    if normalized_type in {"image_ocr", "ocr"}:
        image_refs = _extract_ocr_refs(text, metadata)
        image_ocr = metadata.get("image_ocr") if isinstance(metadata.get("image_ocr"), dict) else {}
        image_count = (metadata.get("parse_summary") or {}).get("image_count") or image_ocr.get("image_count")
        return {
            "type": "image_ocr",
            "text": _clean_preview(_strip_ocr_markers(text), max_chars=800),
            "image_count": image_count,
            "images": image_refs,
        }

    if normalized_type == "formula":
        return {"type": "formula", "text": _clean_preview(text, max_chars=800)}

    if normalized_type == "code":
        return {"type": "code", "text": _clean_preview(text, max_chars=800)}

    return None


def _build_chunk_artifact_quality(content_type: str, artifact: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    diagnostics = build_evidence_item_artifact_diagnostics(
        {"metadata": {"content_type": content_type, "artifact": artifact}}
    )
    return diagnostics if diagnostics.get("structured") else None


def _artifact_issue_feature_flags(
    content_type: str,
    artifact: Optional[Dict[str, Any]],
    artifact_quality: Optional[Dict[str, Any]],
) -> Dict[str, bool]:
    if not artifact_quality or artifact_quality.get("status") not in {"warn", "fail"}:
        return {}

    normalized_type = str(content_type or "").strip().lower()
    artifact_type = str((artifact or {}).get("type") or normalized_type).strip().lower()
    flags = {"has_artifact_issue": True}
    if normalized_type == "table" or artifact_type == "table":
        flags["has_table_artifact_issue"] = True
        if artifact_quality.get("table_missing_structure"):
            flags["has_table_missing_structure"] = True
        if artifact_quality.get("table_missing_source"):
            flags["has_table_missing_source"] = True
    if normalized_type in {"image_ocr", "ocr"} or artifact_type in {"image_ocr", "ocr"}:
        flags["has_ocr_artifact_issue"] = True
        if artifact_quality.get("ocr_missing_source"):
            flags["has_ocr_missing_source"] = True
        if int(artifact_quality.get("ocr_low_confidence_source_count") or 0) > 0:
            flags["has_ocr_low_confidence"] = True
    return flags


def _features_with_artifact_issue_flags(
    features: Dict[str, bool],
    content_type: str,
    artifact: Optional[Dict[str, Any]],
    artifact_quality: Optional[Dict[str, Any]],
) -> Dict[str, bool]:
    merged = dict(features or {})
    merged.update(_artifact_issue_feature_flags(content_type, artifact, artifact_quality))
    return merged


def _features_with_anchor_flags(features: Dict[str, bool], chunk: Dict[str, Any]) -> Dict[str, bool]:
    merged = dict(features or {})
    if not _chunk_has_anchor(chunk):
        merged["has_missing_anchor"] = True
        merged["has_location_issue"] = True
    return merged


def _features_with_size_flags(features: Dict[str, bool], chunk: Dict[str, Any]) -> Dict[str, bool]:
    merged = dict(features or {})
    token_count = _chunk_token_count(chunk)
    if token_count is None:
        return merged
    if token_count < 40:
        merged["has_short_chunk"] = True
        merged["has_size_issue"] = True
    if token_count > 1200:
        merged["has_large_chunk"] = True
        merged["has_size_issue"] = True
    return merged


def _features_for_filtering(
    chunk: Dict[str, Any],
    metadata: Dict[str, Any],
    visual: Optional[Dict[str, Any]] = None,
) -> Dict[str, bool]:
    visual = visual if isinstance(visual, dict) else {}
    text = str(chunk.get("text") or "")
    content_type = metadata.get("content_type") or visual.get("content_type") or "text"
    inferred = _infer_features(text, {**metadata, "content_type": content_type})
    stored_features = metadata.get("features") if isinstance(metadata.get("features"), dict) else {}
    visual_features = visual.get("features") if isinstance(visual.get("features"), dict) else {}
    artifact = metadata.get("artifact") or visual.get("artifact")
    artifact = artifact if isinstance(artifact, dict) else None
    artifact_quality = (
        metadata.get("artifact_quality")
        or visual.get("artifact_quality")
        or _build_chunk_artifact_quality(str(content_type), artifact)
    )
    artifact_quality = artifact_quality if isinstance(artifact_quality, dict) else None
    merged = _features_with_artifact_issue_flags(
        {**inferred, **visual_features, **stored_features},
        str(content_type),
        artifact,
        artifact_quality,
    )
    anchor_probe = dict(chunk)
    anchor_probe["metadata"] = {**metadata, "visual": visual}
    merged = _features_with_anchor_flags(merged, anchor_probe)
    return _features_with_size_flags(merged, anchor_probe)


def enrich_chunks_for_visualization(
    chunks: List[Dict[str, Any]],
    document_text: str,
    parse_metadata: Optional[Dict[str, Any]] = None,
    *,
    document_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Attach compact, visualizable source metadata to chunker output."""
    parse_metadata = parse_metadata or {}
    page_spans = _build_page_spans(parse_metadata)
    parse_summary = build_parse_quality_summary(parse_metadata, document_text)
    enriched: List[Dict[str, Any]] = []
    cursor = 0

    for index, chunk in enumerate(chunks):
        text = str(chunk.get("text") or "")
        original_meta = dict(chunk.get("metadata") or {})
        meta = _compact_metadata(original_meta)

        start = _first_int(chunk.get("start_index"), meta.get("char_start"))
        end = _first_int(chunk.get("end_index"), meta.get("char_end"))
        if start is None or end is None:
            start, end = _find_text_span(document_text, text, cursor)
        cursor = max(cursor, end)

        page_start, page_end = _page_range_for_span(start, end, page_spans)
        section_path = _infer_section_path(text, meta)
        content_type = _infer_content_type(text, meta)
        features = _infer_features(text, {**meta, "content_type": content_type})
        preview = _clean_preview(text)

        artifact = _build_chunk_artifact(text, content_type, original_meta)
        artifact_quality = _build_chunk_artifact_quality(content_type, artifact)
        features = _features_with_artifact_issue_flags(features, content_type, artifact, artifact_quality)
        if (page_start is None or page_end is None) and artifact and artifact.get("type") == "image_ocr":
            ocr_pages = [
                _safe_int(image.get("page"))
                for image in artifact.get("images", [])
                if isinstance(image, dict) and _safe_int(image.get("page")) is not None
            ]
            if ocr_pages:
                page_start = min(ocr_pages)
                page_end = max(ocr_pages)
        features = _features_with_anchor_flags(
            features,
            {
                "metadata": {
                    "page": page_start if page_start == page_end else None,
                    "page_start": page_start,
                    "page_end": page_end,
                    "char_start": start,
                    "char_end": end,
                    "artifact": artifact,
                }
            },
        )
        features = _features_with_size_flags(features, {**chunk, "metadata": meta})
        visual = {
            "preview": preview,
            "char_start": start,
            "char_end": end,
            "page_start": page_start,
            "page_end": page_end,
            "content_type": content_type,
            "section_path": section_path,
            "features": features,
            "artifact": artifact,
            "artifact_quality": artifact_quality,
        }

        meta.update(
            {
                "chunk_index": index,
                "content_type": content_type,
                "section_path": section_path,
                "page": page_start if page_start == page_end else None,
                "page_start": page_start,
                "page_end": page_end,
                "char_start": start,
                "char_end": end,
                "preview": preview,
                "features": features,
                "artifact": artifact,
                "artifact_quality": artifact_quality,
                "visual": visual,
                "parse_summary": parse_summary,
            }
        )
        if document_id:
            meta["document_id"] = document_id

        enriched_chunk = dict(chunk)
        enriched_chunk["chunk_index"] = index
        enriched_chunk["metadata"] = meta
        enriched.append(enriched_chunk)

    return enriched


def build_chunk_preview(chunk: Dict[str, Any], *, include_text: bool = True) -> Dict[str, Any]:
    """Build an API-friendly chunk preview object."""
    metadata = dict(chunk.get("metadata") or {})
    visual = metadata.get("visual") if isinstance(metadata.get("visual"), dict) else {}
    text = str(chunk.get("text") or "")
    section_path = metadata.get("section_path") or visual.get("section_path") or []
    if isinstance(section_path, str):
        section_path = [section_path]
    if not isinstance(section_path, list):
        section_path = []
    content_type = metadata.get("content_type") or visual.get("content_type") or "text"
    artifact = metadata.get("artifact") or visual.get("artifact") or _build_chunk_artifact(text, str(content_type), metadata)
    artifact_quality = (
        metadata.get("artifact_quality")
        or visual.get("artifact_quality")
        or _build_chunk_artifact_quality(str(content_type), artifact)
    )
    features = _features_for_filtering(chunk, metadata, visual)

    item = {
        "id": str(chunk.get("_id") or chunk.get("id") or ""),
        "document_id": chunk.get("document_id") or metadata.get("document_id"),
        "chunk_index": chunk.get("chunk_index"),
        "preview": metadata.get("preview") or visual.get("preview") or _clean_preview(text),
        "content_type": content_type,
        "section_path": [str(part) for part in section_path],
        "page": metadata.get("page"),
        "page_start": metadata.get("page_start") if metadata.get("page_start") is not None else visual.get("page_start"),
        "page_end": metadata.get("page_end") if metadata.get("page_end") is not None else visual.get("page_end"),
        "char_start": metadata.get("char_start") if metadata.get("char_start") is not None else visual.get("char_start"),
        "char_end": metadata.get("char_end") if metadata.get("char_end") is not None else visual.get("char_end"),
        "token_count": metadata.get("token_count"),
        "features": features,
        "artifact": artifact,
        "artifact_quality": artifact_quality,
        "chunker_type": metadata.get("chunker_type"),
        "parse_summary": metadata.get("parse_summary") or {},
    }
    if include_text:
        item["text"] = text
    return item


def build_retrieval_payload_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Build compact chunk metadata safe to store in vector payloads."""
    meta = metadata or {}
    section_path = meta.get("section_path")
    if isinstance(section_path, list):
        section_path = [str(s)[:200] for s in section_path[:12]]
    elif section_path is not None:
        section_path = [str(section_path)[:200]]

    return {
        "content_type": meta.get("content_type", "text"),
        "chunker_type": meta.get("chunker_type"),
        "token_count": meta.get("token_count"),
        "section_path": section_path,
        "page": meta.get("page"),
        "page_start": meta.get("page_start"),
        "page_end": meta.get("page_end"),
        "char_start": meta.get("char_start"),
        "char_end": meta.get("char_end"),
        "preview": meta.get("preview"),
        "artifact": meta.get("artifact"),
        "features": meta.get("features") or {},
        "parse_summary": meta.get("parse_summary") or {},
        "file_type": meta.get("file_type"),
    }


def filter_chunks_for_preview(
    chunks: List[Dict[str, Any]],
    *,
    content_type: Optional[str] = None,
    feature: Optional[str] = None,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter chunks before paginating the chunk preview API."""
    normalized_type = (content_type or "").strip().lower()
    normalized_feature = (feature or "").strip().lower()
    normalized_query = (query or "").strip().lower()
    if normalized_feature and not normalized_feature.startswith("has_"):
        normalized_feature = f"has_{normalized_feature}"

    def flatten(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        if isinstance(value, list):
            return " ".join(flatten(item) for item in value)
        if isinstance(value, dict):
            return " ".join(flatten(item) for item in value.values())
        return str(value)

    def matches(chunk: Dict[str, Any]) -> bool:
        metadata = chunk.get("metadata") or {}
        if normalized_type and normalized_type != "all":
            chunk_type = str(metadata.get("content_type") or "").strip().lower()
            if chunk_type != normalized_type:
                return False
        if normalized_feature and normalized_feature != "all":
            visual = metadata.get("visual") if isinstance(metadata.get("visual"), dict) else {}
            features = _features_for_filtering(chunk, metadata, visual)
            if features.get(normalized_feature) is not True:
                return False
        if normalized_query:
            search_text = " ".join(
                [
                    str(chunk.get("text") or ""),
                    str(metadata.get("preview") or ""),
                    flatten(metadata.get("section_path")),
                    flatten(metadata.get("artifact")),
                ]
            ).lower()
            if normalized_query not in search_text:
                return False
        return True

    return [chunk for chunk in chunks if matches(chunk)]
