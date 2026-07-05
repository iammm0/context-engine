import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from utils.chunk_metadata import build_chunk_preview, build_parse_quality_summary, enrich_chunks_for_visualization


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
    assert "text" not in preview


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
