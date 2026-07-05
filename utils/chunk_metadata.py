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
    has_image_ocr = content_type in {"image_ocr", "ocr"} or "[图片文字]" in text
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
    parse_summary = summarize_parse_metadata(parse_metadata, document_text)
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

        visual = {
            "preview": preview,
            "char_start": start,
            "char_end": end,
            "page_start": page_start,
            "page_end": page_end,
            "content_type": content_type,
            "section_path": section_path,
            "features": features,
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

    item = {
        "id": str(chunk.get("_id") or chunk.get("id") or ""),
        "document_id": chunk.get("document_id") or metadata.get("document_id"),
        "chunk_index": chunk.get("chunk_index"),
        "preview": metadata.get("preview") or visual.get("preview") or _clean_preview(text),
        "content_type": metadata.get("content_type") or visual.get("content_type") or "text",
        "section_path": [str(part) for part in section_path],
        "page": metadata.get("page"),
        "page_start": metadata.get("page_start") if metadata.get("page_start") is not None else visual.get("page_start"),
        "page_end": metadata.get("page_end") if metadata.get("page_end") is not None else visual.get("page_end"),
        "char_start": metadata.get("char_start") if metadata.get("char_start") is not None else visual.get("char_start"),
        "char_end": metadata.get("char_end") if metadata.get("char_end") is not None else visual.get("char_end"),
        "token_count": metadata.get("token_count"),
        "features": metadata.get("features") or visual.get("features") or {},
        "chunker_type": metadata.get("chunker_type"),
        "parse_summary": metadata.get("parse_summary") or {},
    }
    if include_text:
        item["text"] = text
    return item
