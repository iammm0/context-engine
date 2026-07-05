"""Chunk metadata helpers for ingestion, preview, and source citation."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


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


def summarize_parse_metadata(metadata: Dict[str, Any], document_text: str = "") -> Dict[str, Any]:
    """Build a compact document-level parse summary safe to repeat on chunks."""
    image_ocr = metadata.get("image_ocr") if isinstance(metadata.get("image_ocr"), dict) else {}
    page_count = _safe_int(metadata.get("page_count")) or _safe_int(metadata.get("pages"))
    if page_count is None and isinstance(metadata.get("pages"), list):
        page_count = len(metadata["pages"])

    return {
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

    page_count = summary.get("page_count") or 0
    extracted_pages = summary.get("extracted_pages")
    if extracted_pages is None and page_count and len(document_text or "") > 0:
        extracted_pages = page_count

    page_coverage = None
    if page_count and extracted_pages is not None:
        page_coverage = max(0.0, min(1.0, float(extracted_pages) / max(float(page_count), 1.0)))

    warnings: List[str] = []
    score = 100

    text_length = int(summary.get("text_length") or 0)
    if text_length == 0:
        score -= 60
        warnings.append("未提取到正文文本")
    elif text_length < 200:
        score -= 15
        warnings.append("正文文本较短，可能存在解析不完整")

    if page_coverage is not None and page_coverage < 0.9:
        penalty = int((1.0 - page_coverage) * 35)
        score -= max(5, penalty)
        warnings.append(f"页面文本覆盖率偏低：{page_coverage:.0%}")

    image_count = int(summary.get("image_count") or 0)
    ocr_text_length = int(summary.get("ocr_text_length") or 0)
    if image_count > 0 and ocr_text_length == 0:
        score -= 10
        warnings.append("检测到图片但未产生 OCR 文本")

    if chunks and not content_type_counts:
        score -= 10
        warnings.append("未识别到有效切块类型")

    score = max(0, min(100, score))
    return {
        **summary,
        "chunk_count": len(chunks),
        "content_type_counts": content_type_counts,
        "page_coverage": page_coverage,
        "quality_score": score,
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


def _extract_ocr_refs(text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    lookup = _ocr_image_lookup(metadata)
    refs: List[Dict[str, Any]] = []
    for match in _OCR_MARKER_RE.finditer(text or ""):
        page = _safe_int(match.group("page"))
        image_index = _safe_int(match.group("image"))
        image_meta = lookup.get((page, image_index), {})
        if page is None and image_index is None and not image_meta:
            continue
        refs.append(
            {
                "page": page,
                "image_index": image_index,
                "confidence": image_meta.get("confidence"),
                "line_count": image_meta.get("line_count"),
                "text_length": image_meta.get("text_length"),
                "width": image_meta.get("width"),
                "height": image_meta.get("height"),
            }
        )

    if refs:
        return refs

    image_ocr = metadata.get("image_ocr") if isinstance(metadata.get("image_ocr"), dict) else {}
    images = image_ocr.get("images") if isinstance(image_ocr.get("images"), list) else []
    for image in images[:3]:
        if isinstance(image, dict):
            refs.append(
                {
                    "page": _safe_int(image.get("page")),
                    "image_index": _safe_int(image.get("image_index")),
                    "confidence": image.get("confidence"),
                    "line_count": image.get("line_count"),
                    "text_length": image.get("text_length"),
                    "width": image.get("width"),
                    "height": image.get("height"),
                }
            )
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


def _build_chunk_artifact(text: str, content_type: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a compact preview artifact for non-plain-text chunks."""
    normalized_type = (content_type or "text").lower()
    if normalized_type == "table" or bool(_TABLE_RE.search(text or "")):
        table = _extract_markdown_table(text)
        if table:
            return table
        return {
            "type": "table",
            "markdown": _clean_preview(text, max_chars=800),
            "headers": [],
            "rows": [],
            "row_count": None,
            "column_count": None,
        }

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
        if (page_start is None or page_end is None) and artifact and artifact.get("type") == "image_ocr":
            ocr_pages = [
                _safe_int(image.get("page"))
                for image in artifact.get("images", [])
                if isinstance(image, dict) and _safe_int(image.get("page")) is not None
            ]
            if ocr_pages:
                page_start = min(ocr_pages)
                page_end = max(ocr_pages)
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
        "features": metadata.get("features") or visual.get("features") or {},
        "artifact": artifact,
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
