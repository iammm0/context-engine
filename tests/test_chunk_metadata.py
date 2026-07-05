import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from utils.chunk_metadata import (
    build_chunk_preview,
    build_parse_quality_summary,
    build_retrieval_payload_metadata,
    enrich_chunks_for_visualization,
    filter_chunks_for_preview,
)


def test_enrich_chunks_adds_visual_metadata_and_compacts_heavy_fields():
    text = "第一章 概述\n\nRAG uses retrieval before generation.\n\n| 指标 | 数值 |\n| --- | --- |\n| recall | 0.9 |"
    metadata = {
        "parser_type": "legacy",
        "extraction_method": "text_extraction",
        "pages": [{"page": 1, "text": "第一章 概述\n\nRAG uses retrieval before generation."}],
        "tables": [{"markdown": "| 指标 | 数值 |"}],
        "formulas": [],
    }
    chunks = [
        {
            "text": "第一章 概述\n\nRAG uses retrieval before generation.",
            "start_index": 0,
            "end_index": 46,
            "metadata": {"chunker_type": "legacy", "pages": metadata["pages"], "tables": metadata["tables"]},
        },
        {
            "text": "| 指标 | 数值 |\n| --- | --- |\n| recall | 0.9 |",
            "metadata": {"chunker_type": "hybrid", "content_type": "table", "tables": metadata["tables"]},
        },
    ]

    enriched = enrich_chunks_for_visualization(chunks, text, metadata, document_id="doc1")

    first_meta = enriched[0]["metadata"]
    assert first_meta["page"] == 1
    assert first_meta["section_path"] == ["概述"]
    assert first_meta["content_type"] == "text"
    assert first_meta["visual"]["char_start"] == 0
    assert first_meta["parse_summary"]["table_count"] == 1
    assert "pages" not in first_meta
    assert "tables" not in first_meta

    second_meta = enriched[1]["metadata"]
    assert second_meta["content_type"] == "table"
    assert second_meta["features"]["has_table"] is True
    assert second_meta["artifact"]["type"] == "table"
    assert second_meta["artifact"]["headers"] == ["指标", "数值"]
    assert second_meta["artifact"]["rows"] == [["recall", "0.9"]]


def test_build_chunk_preview_uses_visual_metadata_without_full_text():
    chunk = {
        "_id": "chunk1",
        "document_id": "doc1",
        "chunk_index": 0,
        "text": "A long chunk body",
        "metadata": {
            "content_type": "image_ocr",
            "page_start": 2,
            "page_end": 3,
            "preview": "A long chunk body",
            "features": {"has_image_ocr": True},
        },
    }

    preview = build_chunk_preview(chunk, include_text=False)

    assert preview["id"] == "chunk1"
    assert preview["content_type"] == "image_ocr"
    assert preview["page_start"] == 2
    assert preview["page_end"] == 3
    assert preview["features"]["has_image_ocr"] is True
    assert preview["artifact"]["type"] == "image_ocr"
    assert preview["artifact"]["text"] == "A long chunk body"
    assert "text" not in preview


def test_ocr_artifact_tracks_source_image_refs_and_derives_page_range():
    chunk_text = "[图片文字]\n[图片文字 page=3 image=2]\n图中包含召回率 0.92"
    image_ocr = {
        "image_count": 1,
        "ocr_text_length": len(chunk_text),
        "images": [
            {
                "page": 3,
                "image_index": 2,
                "confidence": 0.88,
                "line_count": 4,
                "text_length": 13,
                "width": 640,
                "height": 320,
            }
        ],
    }
    chunks = [{"text": chunk_text, "metadata": {"image_ocr": image_ocr}}]

    enriched = enrich_chunks_for_visualization(chunks, chunk_text, {"image_ocr": image_ocr})

    meta = enriched[0]["metadata"]
    artifact = meta["artifact"]
    assert meta["content_type"] == "image_ocr"
    assert meta["page"] == 3
    assert meta["page_start"] == 3
    assert meta["page_end"] == 3
    assert artifact["type"] == "image_ocr"
    assert artifact["text"] == "图中包含召回率 0.92"
    assert "[图片文字" not in artifact["text"]
    assert artifact["image_count"] == 1
    assert len(artifact["images"]) == 1
    assert artifact["images"][0]["page"] == 3
    assert artifact["images"][0]["image_index"] == 2
    assert artifact["images"][0]["confidence"] == 0.88
    assert artifact["images"][0]["line_count"] == 4
    assert artifact["images"][0]["width"] == 640
    assert artifact["images"][0]["height"] == 320


def test_retrieval_payload_metadata_keeps_compact_artifact_for_evidence_cards():
    metadata = {
        "content_type": "table",
        "section_path": ["A" * 260, "Methods"],
        "page_start": 2,
        "page_end": 2,
        "preview": "table preview",
        "artifact": {
            "type": "table",
            "headers": ["指标", "数值"],
            "rows": [["recall", "0.9"]],
            "row_count": 1,
            "column_count": 2,
        },
        "pages": [{"page": 1, "text": "heavy"}],
        "tables": [{"markdown": "heavy"}],
    }

    payload = build_retrieval_payload_metadata(metadata)

    assert payload["content_type"] == "table"
    assert payload["section_path"] == ["A" * 200, "Methods"]
    assert payload["artifact"]["type"] == "table"
    assert payload["artifact"]["headers"] == ["指标", "数值"]
    assert payload["artifact"]["rows"] == [["recall", "0.9"]]
    assert "pages" not in payload
    assert "tables" not in payload


def test_filter_chunks_for_preview_by_content_type_and_feature():
    chunks = [
        {"text": "intro", "metadata": {"content_type": "text", "features": {}, "section_path": ["Overview"]}},
        {
            "text": "metrics",
            "metadata": {
                "content_type": "table",
                "features": {"has_table": True},
                "artifact": {"headers": ["指标"], "rows": [["recall"]]},
            },
        },
        {"metadata": {"content_type": "image_ocr", "features": {"has_image_ocr": True}}},
    ]

    assert filter_chunks_for_preview(chunks, content_type="table") == [chunks[1]]
    assert filter_chunks_for_preview(chunks, feature="image_ocr") == [chunks[2]]
    assert filter_chunks_for_preview(chunks, content_type="table", feature="has_image_ocr") == []
    assert filter_chunks_for_preview(chunks, query="overview") == [chunks[0]]
    assert filter_chunks_for_preview(chunks, query="recall") == [chunks[1]]
    assert filter_chunks_for_preview(chunks, content_type="table", query="recall") == [chunks[1]]
    assert filter_chunks_for_preview(chunks, content_type="image_ocr", query="recall") == []
    assert filter_chunks_for_preview(chunks, content_type="all") == chunks


def test_build_parse_quality_summary_scores_and_warns_on_low_coverage_ocr_gap():
    summary = build_parse_quality_summary(
        {
            "parser_type": "legacy",
            "extraction_method": "text_extraction",
            "page_count": 10,
            "extracted_pages": 5,
            "image_ocr": {"image_count": 2, "ocr_text_length": 0},
            "tables": [],
            "formulas": [],
        },
        "short text",
        [{"metadata": {"content_type": "text"}}, {"metadata": {"content_type": "table"}}],
    )

    assert summary["page_coverage"] == 0.5
    assert summary["quality_score"] < 100
    assert summary["chunk_count"] == 2
    assert summary["content_type_counts"] == {"text": 1, "table": 1}
    assert any("页面文本覆盖率偏低" in warning for warning in summary["warnings"])
    assert any("未产生 OCR 文本" in warning for warning in summary["warnings"])
    assert summary["risk_level"] == "high"
    assert summary["recommendations"]

    checks = {item["id"]: item for item in summary["quality_checks"]}
    assert checks["page_coverage"]["status"] == "warn"
    assert checks["image_ocr"]["status"] == "warn"
    assert checks["text_extraction"]["status"] == "warn"


def test_build_parse_quality_summary_warns_when_structured_artifacts_are_not_chunked():
    summary = build_parse_quality_summary(
        {
            "parser_type": "mineru",
            "extraction_method": "ocr",
            "page_count": 1,
            "extracted_pages": 1,
            "image_ocr": {"image_count": 0, "ocr_text_length": 0},
            "tables": [{"markdown": "| Metric | Value |\n| --- | --- |\n| recall | 0.9 |"}],
            "formulas": [{"latex": "E=mc^2"}],
        },
        "Structured parsing found a table and formula. " * 8,
        [{"text": "Metric Value recall 0.9 E equals m c squared", "metadata": {"content_type": "text"}}],
    )

    checks = {item["id"]: item for item in summary["quality_checks"]}
    assert summary["risk_level"] == "medium"
    assert summary["quality_score"] == 87
    assert checks["table_chunks"]["status"] == "warn"
    assert checks["formula_chunks"]["status"] == "warn"
    assert any("表格" in item for item in summary["recommendations"])
    assert any("公式" in item for item in summary["recommendations"])
    assert any("解析到表格" in warning for warning in summary["warnings"])
    assert any("解析到公式" in warning for warning in summary["warnings"])
