import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from utils.chunk_metadata import build_chunk_preview, enrich_chunks_for_visualization


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
