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


def test_table_artifact_uses_metadata_when_chunk_text_is_not_markdown_table():
    table_markdown = "| 指标 | 数值 |\n| --- | --- |\n| precision | 0.8 |\n| recall | 0.9 |"
    table_meta = {
        "markdown": table_markdown,
        "page": 4,
        "caption": "模型评估指标",
        "type": "markdown",
        "bbox": [10, 20, 300, 180],
    }
    chunks = [
        {
            "text": "模型评估指标表",
            "metadata": {
                "content_type": "table",
                "tables": [table_meta],
                "token_count": 12,
            },
        }
    ]

    enriched = enrich_chunks_for_visualization(chunks, "模型评估指标表", {"tables": [table_meta]})

    artifact = enriched[0]["metadata"]["artifact"]
    assert artifact["type"] == "table"
    assert artifact["headers"] == ["指标", "数值"]
    assert artifact["rows"] == [["precision", "0.8"], ["recall", "0.9"]]
    assert artifact["row_count"] == 2
    assert artifact["sources"] == [
        {
            "table_index": 1,
            "page": 4,
            "type": "markdown",
            "caption": "模型评估指标",
            "bbox": [10, 20, 300, 180],
        }
    ]


def test_table_artifact_uses_metadata_data_when_markdown_is_missing():
    chunks = [
        {
            "text": "Evaluation metrics",
            "metadata": {
                "content_type": "table",
                "tables": [
                    {
                        "data": [["metric", "value"], ["zero", 0], ["enabled", False]],
                        "page_start": 2,
                        "source": "sheet1",
                    }
                ],
            },
        }
    ]

    enriched = enrich_chunks_for_visualization(chunks, "Evaluation metrics", {})

    artifact = enriched[0]["metadata"]["artifact"]
    assert artifact["type"] == "table"
    assert artifact["headers"] == ["metric", "value"]
    assert artifact["rows"] == [["zero", "0"], ["enabled", "False"]]
    assert artifact["row_count"] == 2
    assert artifact["column_count"] == 2
    assert artifact["sources"][0]["page"] == 2
    assert artifact["sources"][0]["source"] == "sheet1"
    assert artifact["sources"][0]["row_count"] == 2
    assert artifact["sources"][0]["column_count"] == 2
    assert enriched[0]["metadata"]["artifact_quality"]["status"] == "pass"
    assert enriched[0]["metadata"]["visual"]["artifact_quality"]["status"] == "pass"


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
    assert preview["features"]["has_artifact_issue"] is True
    assert preview["features"]["has_ocr_artifact_issue"] is True
    assert preview["artifact"]["type"] == "image_ocr"
    assert preview["artifact"]["text"] == "A long chunk body"
    assert preview["artifact_quality"]["status"] == "warn"
    assert preview["artifact_quality"]["ocr_missing_source"] is True
    assert "text" not in preview


def test_enrich_chunks_marks_artifact_issue_features():
    chunks = [
        {
            "text": "broken table preview",
            "metadata": {"content_type": "table"},
        }
    ]

    enriched = enrich_chunks_for_visualization(chunks, "broken table preview", {})

    features = enriched[0]["metadata"]["features"]
    assert features["has_table"] is True
    assert features["has_artifact_issue"] is True
    assert features["has_table_artifact_issue"] is True
    assert enriched[0]["metadata"]["visual"]["features"]["has_artifact_issue"] is True
    assert enriched[0]["metadata"]["artifact_quality"]["status"] == "warn"


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
                "text": "图中包含召回率 0.92\n更多说明",
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
    assert artifact["images"][0]["low_confidence"] is False
    assert artifact["images"][0]["line_count"] == 4
    assert artifact["images"][0]["text_preview"] == "图中包含召回率 0.92 更多说明"
    assert artifact["images"][0]["width"] == 640
    assert artifact["images"][0]["height"] == 320


def test_ocr_artifact_marks_low_confidence_image_refs_without_markers():
    chunk_text = "[图片文字]\n模糊图中可能包含召回率"
    image_ocr = {
        "image_count": 1,
        "ocr_text_length": len("模糊图中可能包含召回率"),
        "images": [
            {
                "image_index": 1,
                "confidence": 0.42,
                "line_count": 1,
                "text_length": len("模糊图中可能包含召回率"),
                "text_preview": "模糊图中可能包含召回率",
            }
        ],
    }

    enriched = enrich_chunks_for_visualization(
        [{"text": chunk_text, "metadata": {"image_ocr": image_ocr}}],
        chunk_text,
        {"image_ocr": image_ocr},
    )

    image_ref = enriched[0]["metadata"]["artifact"]["images"][0]
    assert image_ref["low_confidence"] is True
    assert image_ref["text_preview"] == "模糊图中可能包含召回率"


def test_ocr_artifact_tracks_word_embedded_image_targets():
    chunk_text = "[图片文字 image=2]\n图中包含利润率 18%"
    image_ocr = {
        "image_count": 2,
        "ocr_text_length": len("图中包含利润率 18%"),
        "images": [
            {"image_index": 1, "target": "media/image1.png", "text_length": 0, "line_count": 0},
            {
                "image_index": 2,
                "target": "media/image2.png",
                "confidence": 0.93,
                "line_count": 2,
                "text_length": len("图中包含利润率 18%"),
            },
        ],
    }

    enriched = enrich_chunks_for_visualization(
        [{"text": chunk_text, "metadata": {"image_ocr": image_ocr}}],
        chunk_text,
        {"image_ocr": image_ocr},
    )

    artifact = enriched[0]["metadata"]["artifact"]
    assert artifact["type"] == "image_ocr"
    assert artifact["text"] == "图中包含利润率 18%"
    assert artifact["images"][0]["image_index"] == 2
    assert artifact["images"][0]["target"] == "media/image2.png"


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
            "sources": [{"table_index": 1, "page": 2, "caption": "指标表"}],
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
    assert payload["artifact"]["sources"] == [{"table_index": 1, "page": 2, "caption": "指标表"}]
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
        {
            "text": "broken table",
            "metadata": {
                "content_type": "table",
                "features": {"has_table": True},
                "artifact": {"type": "table", "headers": [], "rows": [], "sources": []},
            },
        },
        {
            "text": "ocr without source",
            "metadata": {
                "content_type": "image_ocr",
                "features": {},
                "artifact": {"type": "image_ocr", "text": "ocr without source", "images": []},
            },
        },
        {"text": "floating", "metadata": {"content_type": "text", "features": {}}},
        {"text": "anchored", "metadata": {"content_type": "text", "char_start": 0, "char_end": 8}},
        {"text": "short", "metadata": {"content_type": "text", "token_count": 10, "char_start": 8, "char_end": 13}},
        {"text": "large", "metadata": {"content_type": "text", "token_count": 1300, "char_start": 13, "char_end": 18}},
    ]

    assert filter_chunks_for_preview(chunks, content_type="table") == [chunks[1], chunks[3]]
    assert filter_chunks_for_preview(chunks, feature="image_ocr") == [chunks[2], chunks[4]]
    assert filter_chunks_for_preview(chunks, content_type="table", feature="has_image_ocr") == []
    assert filter_chunks_for_preview(chunks, feature="artifact_issue") == [chunks[1], chunks[2], chunks[3], chunks[4]]
    assert filter_chunks_for_preview(chunks, feature="table_artifact_issue") == [chunks[1], chunks[3]]
    assert filter_chunks_for_preview(chunks, feature="ocr_artifact_issue") == [chunks[2], chunks[4]]
    assert filter_chunks_for_preview(chunks, content_type="image_ocr", feature="ocr_artifact_issue") == [chunks[2], chunks[4]]
    assert filter_chunks_for_preview(chunks, feature="missing_anchor") == [chunks[0], chunks[1], chunks[2], chunks[3], chunks[4], chunks[5]]
    assert filter_chunks_for_preview(chunks, feature="short_chunk") == [chunks[7]]
    assert filter_chunks_for_preview(chunks, feature="large_chunk") == [chunks[8]]
    assert filter_chunks_for_preview(chunks, feature="size_issue") == [chunks[7], chunks[8]]
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
        [
            {
                "text": "Metric Value recall 0.9 E equals m c squared",
                "metadata": {"content_type": "text", "char_start": 0, "char_end": 46, "token_count": 80},
            }
        ],
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


def test_build_parse_quality_summary_tracks_structured_artifact_coverage():
    summary = build_parse_quality_summary(
        {
            "parser_type": "pdf",
            "extraction_method": "text_extraction",
            "page_count": 1,
            "extracted_pages": 1,
            "image_ocr": {"image_count": 0, "ocr_text_length": 0},
            "tables": [],
            "formulas": [],
        },
        "Structured artifact diagnostics need enough body text for a clean baseline. " * 5,
        [
            {
                "text": "metrics",
                "metadata": {
                    "content_type": "table",
                    "token_count": 80,
                    "char_start": 0,
                    "char_end": 40,
                    "artifact": {
                        "type": "table",
                        "headers": ["metric", "value"],
                        "rows": [["recall", "0.9"]],
                        "sources": [{"page": 1, "table_index": 1}],
                    },
                },
            },
            {
                "text": "ocr text",
                "metadata": {
                    "content_type": "image_ocr",
                    "token_count": 80,
                    "char_start": 40,
                    "char_end": 80,
                    "artifact": {
                        "type": "image_ocr",
                        "text": "ocr text",
                        "images": [{"image_index": 1, "text_preview": "ocr text", "low_confidence": False}],
                    },
                },
            },
        ],
    )

    checks = {item["id"]: item for item in summary["quality_checks"]}
    assert summary["artifact_expected_count"] == 2
    assert summary["artifact_present_count"] == 2
    assert summary["artifact_missing_count"] == 0
    assert summary["artifact_issue_count"] == 0
    assert summary["artifact_preview_coverage"] == 1
    assert summary["table_artifact_issue_count"] == 0
    assert summary["table_artifact_missing_source_count"] == 0
    assert summary["ocr_artifact_issue_count"] == 0
    assert summary["ocr_artifact_low_confidence_source_count"] == 0
    assert checks["chunk_artifacts"]["status"] == "pass"


def test_build_parse_quality_summary_warns_on_incomplete_structured_artifacts():
    summary = build_parse_quality_summary(
        {
            "parser_type": "pdf",
            "extraction_method": "text_extraction",
            "page_count": 1,
            "extracted_pages": 1,
            "image_ocr": {"image_count": 0, "ocr_text_length": 0},
            "tables": [],
            "formulas": [],
        },
        "Incomplete artifact diagnostics need enough body text for a clean baseline. " * 5,
        [
            {
                "text": "metrics",
                "metadata": {
                    "content_type": "table",
                    "token_count": 80,
                    "char_start": 0,
                    "char_end": 40,
                    "artifact": {"type": "table"},
                },
            },
            {
                "text": "ocr text",
                "metadata": {
                    "content_type": "image_ocr",
                    "token_count": 80,
                    "char_start": 40,
                    "char_end": 80,
                    "artifact": {"type": "image_ocr", "text": "ocr text", "images": []},
                },
            },
        ],
    )

    checks = {item["id"]: item for item in summary["quality_checks"]}
    assert summary["artifact_expected_count"] == 2
    assert summary["artifact_present_count"] == 2
    assert summary["artifact_issue_count"] == 2
    assert summary["table_artifact_issue_count"] == 1
    assert summary["table_artifact_missing_structure_count"] == 1
    assert summary["table_artifact_missing_source_count"] == 1
    assert summary["ocr_artifact_issue_count"] == 1
    assert summary["ocr_artifact_missing_source_count"] == 1
    assert checks["chunk_artifacts"]["status"] == "warn"
    assert checks["chunk_artifacts"]["feature_filter"] == "artifact_issue"
    assert checks["chunk_artifacts"]["filter_label"] == "查看问题切块"
    assert "2 个结构化 chunk 存在 artifact 问题" in checks["chunk_artifacts"]["message"]
    assert "表格 artifact 缺少表头" in checks["chunk_artifacts"]["message"]
    assert "表格 artifact 缺少页码或来源" in checks["chunk_artifacts"]["message"]
    assert any("结构化 artifact 信息不完整" in warning for warning in summary["warnings"])


def test_build_parse_quality_summary_scores_ocr_coverage_and_confidence():
    summary = build_parse_quality_summary(
        {
            "parser_type": "pdf",
            "extraction_method": "text_extraction",
            "page_count": 1,
            "extracted_pages": 1,
            "image_ocr": {
                "image_count": 3,
                "ocr_text_length": 80,
                "images": [
                    {"text_length": 40, "line_count": 3, "confidence": 0.92},
                    {"text_length": 0, "line_count": 0, "confidence": 0.0},
                    {"text_length": 40, "line_count": 2, "confidence": 0.42},
                ],
            },
            "tables": [],
            "formulas": [],
        },
        "OCR quality diagnostics need enough body text for a clean baseline. " * 5,
        [{"metadata": {"content_type": "image_ocr"}}],
    )

    checks = {item["id"]: item for item in summary["quality_checks"]}
    assert summary["ocr_recognized_images"] == 2
    assert summary["ocr_empty_images"] == 1
    assert summary["ocr_low_confidence_images"] == 1
    assert round(summary["ocr_image_coverage"], 2) == 0.67
    assert round(summary["ocr_avg_confidence"], 2) == 0.67
    assert summary["risk_level"] == "medium"
    assert checks["image_ocr"]["status"] == "warn"
    assert checks["ocr_confidence"]["status"] == "warn"
    assert any("OCR 覆盖率" in warning for warning in summary["warnings"])
    assert any("OCR 置信度" in warning for warning in summary["warnings"])


def test_build_parse_quality_summary_scores_chunk_size_and_anchor_coverage():
    summary = build_parse_quality_summary(
        {
            "parser_type": "pdf",
            "extraction_method": "text_extraction",
            "page_count": 1,
            "extracted_pages": 1,
            "image_ocr": {"image_count": 0, "ocr_text_length": 0},
            "tables": [],
            "formulas": [],
        },
        "Chunk quality diagnostics need enough body text for a clean parse score. " * 5,
        [
            {"text": "tiny", "metadata": {"content_type": "text", "token_count": 8}},
            {
                "text": "healthy chunk",
                "metadata": {"content_type": "text", "token_count": 120, "char_start": 0, "char_end": 80},
            },
            {
                "text": "oversized chunk",
                "metadata": {"content_type": "text", "token_count": 1400, "char_start": 80, "char_end": 160},
            },
        ],
    )

    checks = {item["id"]: item for item in summary["quality_checks"]}
    assert summary["chunk_anchor_count"] == 2
    assert summary["chunk_missing_anchor_count"] == 1
    assert round(summary["chunk_anchor_coverage"], 2) == 0.67
    assert summary["chunk_token_min"] == 8
    assert summary["chunk_token_max"] == 1400
    assert summary["chunk_token_avg"] == 509.3
    assert summary["chunk_short_count"] == 1
    assert summary["chunk_large_count"] == 1
    assert checks["chunk_anchors"]["status"] == "warn"
    assert checks["chunk_anchors"]["feature_filter"] == "missing_anchor"
    assert checks["chunk_anchors"]["filter_label"] == "查看缺定位切块"
    assert checks["chunk_size"]["status"] == "warn"
    assert checks["chunk_size"]["feature_filter"] == "size_issue"
    assert checks["chunk_size"]["filter_label"] == "查看尺寸异常切块"
    assert any("切块定位覆盖率偏低" in warning for warning in summary["warnings"])
    assert any("切块大小分布不均" in warning for warning in summary["warnings"])
