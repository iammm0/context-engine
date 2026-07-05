import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from models.rag import EvidenceItem
from services.query_planner import query_planner
from utils.citation import extract_citation_ids, format_evidence_context, validate_citations


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
                            "confidence": 0.88,
                            "line_count": 4,
                            "width": 640,
                            "height": 320,
                            "target": "media/image2.png",
                        }
                    ],
                },
            },
        )
    ]

    context = format_evidence_context(evidence)
    assert "[S1]" in context
    assert "Demo" in context
    assert "证据类型: table" in context
    assert "pages 1-2" in context
    assert "结构化证据: table" in context
    assert "列: 指标, 数值" in context
    assert "table sources: pages 1-2, table 2, caption 指标表, type markdown" in context
    assert "样例行: recall | 0.9" in context
    assert "结构化证据: image_ocr" in context
    assert "图片来源: page 3, image 2, confidence 88%, 4 lines, 640x320, media/image2.png" in context
    assert extract_citation_ids("Answer [S1] and [S2]") == ["S1", "S2"]
    assert validate_citations("Answer [S1]", evidence) == []
    assert validate_citations("Answer [S3]", evidence)


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
