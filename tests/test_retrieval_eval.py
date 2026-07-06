import os
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from eval.retrieval_eval import (
    _citation_quality_for_item,
    _to_markdown,
    build_artifact_diagnostics,
    results_to_evidence_items,
    summarize_artifact_diagnostics,
    summarize_citation_quality,
)


def _result(
    *,
    chunk_index,
    content_type="text",
    artifact=None,
    source_locator=None,
    document_id="doc1",
    score=0.9,
):
    metadata = {"content_type": content_type, "page_start": 2}
    if artifact is not None:
        metadata["artifact"] = artifact
    if source_locator is not None:
        metadata["source_locator"] = source_locator
    return {
        "score": score,
        "payload": {
            "text": f"chunk {chunk_index}",
            "document_id": document_id,
            "chunk_id": f"chunk-{chunk_index}",
            "chunk_index": chunk_index,
            "filename": "report.pdf",
            "metadata": metadata,
        },
    }


def test_build_artifact_diagnostics_tracks_gold_and_structured_artifacts():
    table_locator = {
        "source_type": "table",
        "page_start": 2,
        "page_end": 2,
        "anchor_count": 2,
        "has_table_source": True,
        "has_bbox": True,
        "anchors": [
            {"type": "page_range", "page_start": 2, "page_end": 2},
            {"type": "table", "page": 2, "table_index": 1, "bbox": [10, 20, 300, 180]},
        ],
    }
    ocr_locator = {
        "source_type": "image_ocr",
        "page_start": 3,
        "page_end": 3,
        "anchor_count": 2,
        "has_image_source": True,
        "has_bbox": True,
        "anchors": [
            {"type": "page_range", "page_start": 3, "page_end": 3},
            {"type": "image", "page": 3, "image_index": 2, "bbox": [20, 30, 420, 260]},
        ],
    }
    text_locator = {
        "source_type": "text",
        "page_start": 2,
        "page_end": 2,
        "anchor_count": 1,
        "anchors": [{"type": "page_range", "page_start": 2, "page_end": 2}],
    }
    table_artifact = {
        "type": "table",
        "headers": ["metric", "value"],
        "rows": [["recall", "0.9"]],
        "sources": [{"page": 2, "table_index": 1}],
    }
    ocr_artifact = {
        "type": "image_ocr",
        "text": "chart says recall is 0.92",
        "images": [
            {
                "page": 3,
                "image_index": 2,
                "confidence": 0.8,
                "low_confidence": True,
            }
        ],
    }
    results = [
        _result(chunk_index=2, content_type="table", artifact=table_artifact, source_locator=table_locator),
        _result(chunk_index=5, content_type="image_ocr", artifact=ocr_artifact, source_locator=ocr_locator),
        _result(chunk_index=6, content_type="table"),
        _result(chunk_index=9, document_id="doc2", source_locator=text_locator),
    ]

    diagnostics = build_artifact_diagnostics(
        results,
        gold_doc="doc1",
        gold_indices=[2, 5, 8],
        required_artifact_types=["table", "image_ocr", "formula"],
    )

    assert diagnostics["gold_found_chunk_indices"] == [2, 5]
    assert diagnostics["gold_missing_chunk_indices"] == [8]
    assert diagnostics["gold_coverage"] == 0.6667
    assert diagnostics["gold_hit_artifact_coverage"] == 1.0
    assert diagnostics["gold_hit_source_locator_coverage"] == 1.0
    assert diagnostics["artifact_coverage"] == 0.5
    assert diagnostics["source_locator_coverage"] == 0.75
    assert diagnostics["structured_evidence_count"] == 3
    assert diagnostics["structured_artifact_count"] == 2
    assert diagnostics["structured_source_locator_count"] == 2
    assert diagnostics["structured_source_locator_coverage"] == 0.6667
    assert diagnostics["missing_source_locator_count"] == 1
    assert diagnostics["structured_missing_source_locator_count"] == 1
    assert diagnostics["bbox_source_locator_count"] == 2
    assert diagnostics["table_source_locator_count"] == 1
    assert diagnostics["ocr_source_locator_count"] == 1
    assert diagnostics["source_anchor_count"] == 5
    assert diagnostics["table_artifact_complete_count"] == 1
    assert diagnostics["table_artifact_with_source_count"] == 1
    assert diagnostics["ocr_artifact_with_source_count"] == 1
    assert diagnostics["ocr_low_confidence_source_count"] == 1
    assert diagnostics["ocr_average_confidence"] == 0.8
    assert diagnostics["missing_required_artifact_types"] == ["formula"]


def test_summarize_artifact_diagnostics_aggregates_counts_and_ratios():
    first = {
        "retrieved_count": 2,
        "gold_count": 2,
        "gold_hit_count": 1,
        "gold_found_count": 1,
        "gold_hit_artifact_count": 1,
        "gold_hit_source_locator_count": 1,
        "artifact_evidence_count": 1,
        "structured_evidence_count": 1,
        "structured_artifact_count": 1,
        "source_locator_count": 1,
        "structured_source_locator_count": 1,
        "missing_source_locator_count": 1,
        "structured_missing_source_locator_count": 0,
        "bbox_source_locator_count": 1,
        "table_source_locator_count": 1,
        "ocr_source_locator_count": 0,
        "source_anchor_count": 2,
        "table_artifact_count": 1,
        "table_artifact_complete_count": 1,
        "table_artifact_with_source_count": 1,
        "ocr_artifact_count": 0,
        "ocr_artifact_with_source_count": 0,
        "ocr_low_confidence_source_count": 0,
        "gold_coverage": 0.5,
        "gold_hit_artifact_coverage": 1.0,
        "gold_hit_source_locator_coverage": 1.0,
        "artifact_coverage": 0.5,
        "structured_artifact_coverage": 1.0,
        "source_locator_coverage": 0.5,
        "structured_source_locator_coverage": 1.0,
        "ocr_average_confidence": None,
        "artifact_type_counts": {"table": 1},
        "missing_required_artifact_types": ["image_ocr"],
    }
    second = dict(first)
    second.update(
        {
            "gold_coverage": 1.0,
            "artifact_coverage": 1.0,
            "structured_evidence_count": 2,
            "structured_artifact_count": 2,
            "source_locator_count": 2,
            "structured_source_locator_count": 1,
            "missing_source_locator_count": 0,
            "structured_missing_source_locator_count": 1,
            "bbox_source_locator_count": 1,
            "table_source_locator_count": 0,
            "ocr_source_locator_count": 1,
            "source_anchor_count": 3,
            "source_locator_coverage": 1.0,
            "structured_source_locator_coverage": 0.5,
            "artifact_type_counts": {"image_ocr": 2},
            "missing_required_artifact_types": [],
            "ocr_artifact_count": 2,
            "ocr_artifact_with_source_count": 2,
            "ocr_average_confidence": 0.75,
        }
    )

    summary = summarize_artifact_diagnostics([first, second])

    assert summary["evaluated_count"] == 2
    assert summary["retrieved_count"] == 4
    assert summary["avg_gold_coverage"] == 0.75
    assert summary["avg_gold_hit_source_locator_coverage"] == 1.0
    assert summary["avg_artifact_coverage"] == 0.75
    assert summary["avg_source_locator_coverage"] == 0.75
    assert summary["avg_structured_source_locator_coverage"] == 0.75
    assert summary["source_locator_count"] == 3
    assert summary["structured_missing_source_locator_count"] == 1
    assert summary["bbox_source_locator_count"] == 2
    assert summary["table_source_locator_count"] == 1
    assert summary["ocr_source_locator_count"] == 1
    assert summary["source_anchor_count"] == 5
    assert summary["avg_ocr_average_confidence"] == 0.75
    assert summary["artifact_type_counts"] == {"table": 1, "image_ocr": 2}
    assert summary["missing_required_artifact_types"] == ["image_ocr"]


def test_results_to_evidence_items_supports_citation_quality():
    results = [
        _result(chunk_index=1, score=0.9),
        _result(chunk_index=2, score=0.8),
    ]

    evidence = results_to_evidence_items(results)
    assert [item["id"] for item in evidence] == ["S1", "S2"]
    assert evidence[0]["chunk_index"] == 1
    assert evidence[0]["page"] == 2

    citation_quality = _citation_quality_for_item({"answer": "Use [S1] and missing [S3]."}, results)
    assert citation_quality["status"] == "invalid"
    assert citation_quality["valid_citation_ids"] == ["S1"]
    assert citation_quality["invalid_citation_ids"] == ["S3"]

    summary = summarize_citation_quality([citation_quality])
    assert summary["evaluated_count"] == 1
    assert summary["status_counts"] == {"invalid": 1}
    assert summary["avg_coverage"] == 0.5
    assert summary["invalid_citation_count"] == 1


def test_to_markdown_includes_artifact_and_citation_quality_sections():
    markdown = _to_markdown(
        {
            "total": 1,
            "ks": [5],
            "prefetch_k": 20,
            "score_threshold": 0.7,
            "metrics": {
                "5": {"recall_at_k": 1, "precision_at_k": 0.2, "ndcg_at_k": 1},
                "mrr": 1,
                "citation": {"citation_recall": 1, "citation_precision": 0.2},
                "artifact": {
                    "evaluated_count": 1,
                    "avg_gold_coverage": 1,
                    "avg_artifact_coverage": 0.5,
                    "avg_source_locator_coverage": 0.75,
                    "avg_structured_source_locator_coverage": 0.5,
                    "source_locator_count": 3,
                    "structured_missing_source_locator_count": 1,
                    "bbox_source_locator_count": 2,
                    "missing_required_artifact_types": ["image_ocr"],
                },
                "citation_quality": {
                    "evaluated_count": 1,
                    "status_counts": {"complete": 1},
                    "avg_coverage": 1,
                    "invalid_citation_count": 0,
                    "duplicate_citation_count": 0,
                    "warning_count": 0,
                },
            },
        }
    )

    assert "## Artifact Quality" in markdown
    assert "| avg_artifact_coverage | 0.5000 |" in markdown
    assert "| avg_source_locator_coverage | 0.7500 |" in markdown
    assert "| structured_missing_source_locator_count | 1 |" in markdown
    assert "| missing_required_artifact_types | image_ocr |" in markdown
    assert "## Citation Quality" in markdown
    assert '| status_counts | {"complete": 1} |' in markdown
