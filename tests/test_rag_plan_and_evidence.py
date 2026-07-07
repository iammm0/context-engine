import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from models.rag import EvidenceItem
from services.query_planner import query_planner
from utils.citation import build_citation_diagnostics, build_citation_policy_context, extract_citation_ids, format_evidence_context, validate_citations


def test_evidence_format_and_citation_validation():
    evidence = [
        EvidenceItem(
            id="S1",
            text="RAG uses retrieval before generation.",
            document_id="doc1",
            chunk_id="chunk1",
            chunk_index=0,
            document_title="Demo",
            score=0.9,
            retrieval_type="vector",
            metadata={
                "content_type": "table",
                "page_start": 1,
                "page_end": 2,
                "artifact": {
                    "type": "table",
                    "headers": ["指标", "数值"],
                    "rows": [["recall", "0.9"]],
                    "row_count": 1,
                    "column_count": 2,
                    "sources": [{"table_index": 2, "page": 1, "page_end": 2, "caption": "指标表", "type": "markdown"}],
                },
            },
        ),
        EvidenceItem(
            id="S2",
            text="图中包含召回率 0.92",
            document_id="doc1",
            chunk_id="chunk2",
            chunk_index=1,
            document_title="Demo",
            score=0.8,
            retrieval_type="vector",
            metadata={
                "content_type": "image_ocr",
                "page_start": 3,
                "page_end": 3,
                "artifact": {
                    "type": "image_ocr",
                    "text": "图中包含召回率 0.92",
                    "image_count": 1,
                    "images": [
                        {
                            "page": 3,
                            "image_index": 2,
                            "confidence": 0.42,
                            "line_count": 4,
                            "text_length": 12,
                            "text_preview": "图中包含召回率 0.92",
                            "low_confidence": True,
                            "width": 640,
                            "height": 320,
                            "target": "media/image2.png",
                            "bbox": [10, 20, 300, 180],
                        }
                    ],
                },
                "source_locator": {
                    "source_type": "image_ocr",
                    "page_start": 3,
                    "page_end": 3,
                    "anchor_count": 3,
                    "has_image_source": True,
                    "has_bbox": True,
                    "anchors": [
                        {"type": "page_range", "page_start": 3, "page_end": 3},
                        {"type": "image", "page": 3, "image_index": 2, "bbox": [10, 20, 300, 180]},
                    ],
                },
                "artifact_quality": {
                    "status": "warn",
                    "warnings": ["1 个 OCR 图片来源置信度偏低"],
                },
                "quality_notes": ["OCR 图片来源置信度偏低，引用前需要人工复核。"],
            },
        )
    ]

    context = format_evidence_context(evidence)
    assert "source locator: page 3; image source refs; bbox; 3 anchors" in context
    assert "[S1]" in context
    assert "Demo" in context
    assert "证据类型: table" in context
    assert "pages 1-2" in context
    assert "结构化证据: table" in context
    assert "列: 指标, 数值" in context
    assert "table sources: pages 1-2, table 2, caption 指标表, type markdown" in context
    assert "样例行: recall | 0.9" in context
    assert "结构化证据: image_ocr" in context
    assert "artifact质量: 1 个 OCR 图片来源置信度偏低" in context
    assert "质量提示: OCR 图片来源置信度偏低，引用前需要人工复核。" in context
    assert (
        "图片来源: page 3, image 2, confidence 42%, 4 lines, 12 chars, 640x320, "
        "media/image2.png, bbox [10, 20, 300, 180], low confidence, text 图中包含召回率 0.92"
    ) in context
    assert extract_citation_ids("Answer [S1] and [S2]") == ["S1", "S2"]
    assert any("缺少统一来源定位" in warning for warning in validate_citations("Answer [S1]", evidence))
    assert validate_citations("Answer [S3]", evidence)
    diagnostics = build_citation_diagnostics("Answer [S1] and repeat [S1]", evidence)
    assert diagnostics["status"] == "partial"
    assert diagnostics["evidence_count"] == 2
    assert diagnostics["used_citation_ids"] == ["S1"]
    assert diagnostics["valid_citation_ids"] == ["S1"]
    assert diagnostics["invalid_citation_ids"] == []
    assert diagnostics["duplicate_citation_ids"] == ["S1"]
    assert diagnostics["unused_evidence_ids"] == ["S2"]
    assert diagnostics["unreferenced_top_evidence_ids"] == ["S2"]
    assert diagnostics["unreferenced_top_evidence"][0]["id"] == "S2"
    assert diagnostics["unreferenced_top_evidence"][0]["document_id"] == "doc1"
    assert diagnostics["unreferenced_top_evidence"][0]["chunk_id"] == "chunk2"
    assert diagnostics["unreferenced_top_evidence"][0]["chunk_index"] == 1
    assert diagnostics["unreferenced_top_evidence"][0]["page_start"] == 3
    assert diagnostics["unreferenced_top_evidence"][0]["content_type"] == "image_ocr"
    assert diagnostics["unreferenced_top_evidence"][0]["source_locator"]["has_image_source"] is True
    assert diagnostics["unreferenced_top_evidence"][0]["source_locator"]["has_bbox"] is True
    assert diagnostics["unreferenced_top_evidence"][0]["quality_notes"] == ["OCR 图片来源置信度偏低，引用前需要人工复核。"]
    assert diagnostics["unreferenced_top_evidence"][0]["preview"]
    assert diagnostics["coverage"] == 0.5
    assert diagnostics["cited_structured_evidence_count"] == 1
    assert diagnostics["cited_missing_source_locator_ids"] == ["S1"]
    assert diagnostics["cited_artifact_warning_ids"] == []
    assert diagnostics["cited_low_confidence_ocr_ids"] == []
    assert diagnostics["cited_risky_evidence"][0]["id"] == "S1"
    assert diagnostics["cited_risky_evidence"][0]["chunk_id"] == "chunk1"
    assert diagnostics["cited_risky_evidence"][0]["risk_reasons"] == ["missing_source_locator"]
    assert diagnostics["cited_risky_evidence"][0]["content_type"] == "table"
    assert any("重复引用" in warning for warning in diagnostics["warnings"])
    assert any("缺少统一来源定位" in warning for warning in diagnostics["warnings"])
    assert diagnostics["risk_level"] == "medium"
    assert any("未引用的高分证据: S2" in item for item in diagnostics["recommendations"])

    ocr_diagnostics = build_citation_diagnostics("Use OCR [S2].", [evidence[1]])
    assert ocr_diagnostics["status"] == "complete"
    assert ocr_diagnostics["risk_level"] == "medium"
    assert ocr_diagnostics["coverage"] == 1
    assert ocr_diagnostics["cited_structured_evidence_count"] == 1
    assert ocr_diagnostics["cited_missing_source_locator_ids"] == []
    assert ocr_diagnostics["cited_artifact_warning_ids"] == ["S2"]
    assert ocr_diagnostics["cited_low_confidence_ocr_ids"] == ["S2"]
    assert ocr_diagnostics["cited_risky_evidence"][0]["id"] == "S2"
    assert ocr_diagnostics["cited_risky_evidence"][0]["risk_reasons"] == ["artifact_warning", "low_confidence_ocr"]
    assert ocr_diagnostics["cited_risky_evidence"][0]["source_locator"]["has_image_source"] is True
    assert ocr_diagnostics["cited_risky_evidence"][0]["artifact_quality"]["status"] == "warn"
    assert ocr_diagnostics["cited_risky_evidence"][0]["quality_notes"] == ["OCR 图片来源置信度偏低，引用前需要人工复核。"]
    assert any("解析质量提醒" in warning for warning in ocr_diagnostics["warnings"])
    assert any("低置信 OCR" in warning for warning in ocr_diagnostics["warnings"])

    policy = build_citation_policy_context(evidence, {"status": "warn", "warnings": ["OCR证据需要复核"]})
    assert "只能使用以下证据编号: S1, S2" in policy
    assert "每个关键事实、数据、结论或对表格/OCR内容的转述后" in policy
    assert "表格、图片/OCR、公式或代码证据包括: S1, S2" in policy
    assert "带原文定位的证据包括: S2" in policy
    assert "以下证据存在解析质量提醒，引用时要谨慎表述: S2" in policy
    assert "证据质量提醒: OCR证据需要复核" in policy


def test_query_planner_rewrites_only_complex_queries():
    simple = query_planner.build_plan("RAG 是什么？", runtime_modules={"query_rewrite_enabled": True})
    assert simple.need_rewrite is False
    assert simple.rewritten_queries == ["RAG 是什么？"]

    complex_plan = query_planner.build_plan(
        "请对比向量检索和关键词检索的差异、优缺点，并总结适用场景。",
        runtime_modules={"query_rewrite_enabled": True},
    )
    assert complex_plan.need_rewrite is True
    assert complex_plan.final_k >= 20
    assert len(complex_plan.rewritten_queries) >= 2


def test_citation_diagnostics_marks_high_risk_invalid_and_no_evidence():
    evidence = [
        EvidenceItem(
            id="S1",
            text="Supported fact.",
            document_id="doc1",
            chunk_id="chunk1",
            score=0.9,
            retrieval_type="vector",
            metadata={"preview": "Supported fact."},
        )
    ]

    invalid = build_citation_diagnostics("Answer cites missing [S9].", evidence)
    assert invalid["status"] == "invalid"
    assert invalid["risk_level"] == "high"
    assert invalid["invalid_citation_ids"] == ["S9"]
    assert any("不存在的证据编号" in item for item in invalid["recommendations"])

    missing = build_citation_diagnostics("Answer has no evidence citation.", evidence)
    assert missing["status"] == "missing"
    assert missing["risk_level"] == "high"
    assert any("关键事实补充至少一个证据编号" in item for item in missing["recommendations"])

    no_evidence = build_citation_diagnostics("Answer without retrieved evidence.", [])
    assert no_evidence["status"] == "no_evidence"
    assert no_evidence["risk_level"] == "high"
    assert any("未检索到可引用证据" in item for item in no_evidence["recommendations"])
    assert "当前没有可用证据" in build_citation_policy_context([])


def test_rrf_merge_prefers_cross_modal_hits():
    from retrieval.fusion import merge_results_rrf

    vector = [
        {"id": "a", "score": 0.9, "payload": {"chunk_id": "a", "text": "alpha"}},
        {"id": "b", "score": 0.8, "payload": {"chunk_id": "b", "text": "beta"}},
    ]
    keyword = [
        {"id": "b", "score": 2.0, "payload": {"chunk_id": "b", "text": "beta"}},
        {"id": "c", "score": 1.0, "payload": {"chunk_id": "c", "text": "gamma"}},
    ]

    merged = merge_results_rrf([("vector", vector, 1.0), ("keyword", keyword, 0.8)])
    assert {item["payload"]["chunk_id"] for item in merged} == {"a", "b", "c"}
    hybrid = next(item for item in merged if item["payload"]["chunk_id"] == "b")
    assert hybrid["payload"]["retrieval_type"] == "hybrid"


def test_agent_workflow_execution_groups_respect_summary_last():
    from agents.workflow.agent_workflow import AgentWorkflow

    workflow = AgentWorkflow()
    groups = workflow._build_execution_groups(
        ["document_retrieval", "concept_explanation", "critic", "summary"],
        {
            "critic": ["document_retrieval", "concept_explanation"],
            "summary": ["document_retrieval", "concept_explanation", "critic"],
        },
        [],
    )
    assert groups[0] == ["document_retrieval"]
    assert groups[-1] == ["summary"]
    assert ["critic"] in groups
