import os
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from models.rag import EvidenceItem
from utils.evidence_quality import (
    annotate_evidence_artifact_quality,
    build_evidence_item_artifact_diagnostics,
    build_evidence_quality_diagnostics,
)


def test_evidence_quality_passes_complete_structured_artifacts():
    evidence = [
        EvidenceItem(
            id="S1",
            text="指标表显示 recall 为 0.9",
            document_id="doc1",
            chunk_index=1,
            score=0.9,
            metadata={
                "content_type": "table",
                "artifact": {
                    "type": "table",
                    "headers": ["指标", "数值"],
                    "rows": [["recall", "0.9"]],
                    "sources": [{"page": 2, "table_index": 1}],
                },
            },
        ),
        EvidenceItem(
            id="S2",
            text="图中包含召回率 0.92",
            document_id="doc1",
            chunk_index=2,
            score=0.8,
            metadata={
                "content_type": "image_ocr",
                "artifact": {
                    "type": "image_ocr",
                    "text": "图中包含召回率 0.92",
                    "images": [
                        {
                            "page": 3,
                            "image_index": 1,
                            "confidence": 0.88,
                            "low_confidence": False,
                        }
                    ],
                },
            },
        ),
    ]

    diagnostics = build_evidence_quality_diagnostics(evidence)

    assert diagnostics["status"] == "pass"
    assert diagnostics["risk_level"] == "low"
    assert diagnostics["evidence_count"] == 2
    assert diagnostics["artifact_coverage"] == 1
    assert diagnostics["structured_artifact_coverage"] == 1
    assert diagnostics["table_missing_structure_count"] == 0
    assert diagnostics["table_missing_source_count"] == 0
    assert diagnostics["ocr_missing_source_count"] == 0
    assert diagnostics["ocr_avg_confidence"] == 0.88
    assert diagnostics["warnings"] == []


def test_evidence_quality_warns_on_incomplete_table_and_ocr_artifacts():
    evidence = [
        {
            "id": "S1",
            "text": "表格证据",
            "score": 0.7,
            "metadata": {
                "content_type": "table",
                "artifact": {"type": "table", "sources": []},
            },
        },
        {
            "id": "S2",
            "text": "OCR证据",
            "score": 0.6,
            "metadata": {
                "content_type": "image_ocr",
                "artifact": {
                    "type": "image_ocr",
                    "text": "模糊图片文字",
                    "images": [
                        {
                            "page": 4,
                            "image_index": 2,
                            "confidence": 0.42,
                            "low_confidence": True,
                        }
                    ],
                },
            },
        },
        {
            "id": "S3",
            "text": "公式证据",
            "score": 0.5,
            "metadata": {"content_type": "formula"},
        },
    ]

    diagnostics = build_evidence_quality_diagnostics(evidence)

    assert diagnostics["status"] == "warn"
    assert diagnostics["risk_level"] == "high"
    assert diagnostics["artifact_count"] == 2
    assert diagnostics["structured_evidence_count"] == 3
    assert diagnostics["structured_artifact_count"] == 2
    assert diagnostics["structured_artifact_coverage"] == 0.6667
    assert diagnostics["table_missing_structure_count"] == 1
    assert diagnostics["table_missing_source_count"] == 1
    assert diagnostics["ocr_low_confidence_source_count"] == 1
    assert any("结构化证据缺少 artifact" in warning for warning in diagnostics["warnings"])
    assert any("表格证据缺少表头" in warning for warning in diagnostics["warnings"])
    assert any("置信度偏低" in warning for warning in diagnostics["warnings"])


def test_evidence_item_artifact_diagnostics_marks_specific_table_gap():
    item = {
        "id": "S1",
        "text": "表格证据",
        "metadata": {
            "content_type": "table",
            "artifact": {"type": "table", "sources": []},
        },
    }

    diagnostics = build_evidence_item_artifact_diagnostics(item)

    assert diagnostics["status"] == "warn"
    assert diagnostics["risk_level"] == "high"
    assert diagnostics["structured"] is True
    assert diagnostics["table_missing_structure"] is True
    assert diagnostics["table_missing_source"] is True
    assert diagnostics["ocr_missing_source"] is False
    assert "表格证据缺少表头、样例行或 Markdown 预览" in diagnostics["warnings"]
    assert "表格证据缺少页码或表格来源" in diagnostics["warnings"]


def test_annotate_evidence_artifact_quality_only_adds_structured_metadata():
    text_item = EvidenceItem(
        id="S1",
        text="普通文本证据",
        document_id="doc1",
        score=0.9,
        metadata={"content_type": "text"},
    )
    table_item = EvidenceItem(
        id="S2",
        text="表格证据",
        document_id="doc1",
        score=0.8,
        metadata={
            "content_type": "table",
            "artifact": {
                "type": "table",
                "headers": ["指标", "数值"],
                "rows": [["recall", "0.9"]],
                "sources": [{"page": 2, "table_index": 1}],
            },
        },
    )

    annotate_evidence_artifact_quality([text_item, table_item])

    assert "artifact_quality" not in text_item.metadata
    assert table_item.metadata["artifact_quality"]["status"] == "pass"
    assert table_item.metadata["artifact_quality"]["structured"] is True
    assert table_item.metadata["artifact_quality"]["warnings"] == []


def test_evidence_quality_marks_empty_evidence_as_high_risk():
    diagnostics = build_evidence_quality_diagnostics([])

    assert diagnostics["status"] == "no_evidence"
    assert diagnostics["risk_level"] == "high"
    assert diagnostics["evidence_count"] == 0
    assert diagnostics["artifact_coverage"] is None
    assert diagnostics["structured_artifact_coverage"] is None
