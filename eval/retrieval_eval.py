import asyncio
import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.rag_retriever import RAGRetriever
from utils.citation import build_citation_diagnostics
from utils.logger import logger


STRUCTURED_ARTIFACT_TYPES = {"table", "image_ocr", "ocr", "formula", "code"}


def _load_dataset(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _safe_ratio(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _as_int_list(values: Any) -> List[int]:
    if not isinstance(values, list):
        return []
    out: List[int] = []
    for value in values:
        if isinstance(value, int):
            out.append(value)
    return out


def _result_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    payload = result.get("payload") if isinstance(result, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _metadata_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    metadata = payload.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _artifact_from_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    metadata = _metadata_from_payload(payload)
    artifact = metadata.get("artifact")
    if isinstance(artifact, dict):
        return artifact

    artifact = payload.get("artifact")
    if isinstance(artifact, dict):
        return artifact

    visual = metadata.get("visual")
    if isinstance(visual, dict) and isinstance(visual.get("artifact"), dict):
        return visual["artifact"]
    return None


def _source_locator_from_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    metadata = _metadata_from_payload(payload)
    locator = metadata.get("source_locator")
    if isinstance(locator, dict):
        return locator

    locator = payload.get("source_locator")
    if isinstance(locator, dict):
        return locator

    visual = metadata.get("visual")
    if isinstance(visual, dict) and isinstance(visual.get("source_locator"), dict):
        return visual["source_locator"]
    return None


def _source_locator_anchor_count(locator: Optional[Dict[str, Any]]) -> int:
    if not isinstance(locator, dict):
        return 0
    anchors = locator.get("anchors")
    anchor_list_count = len(anchors) if isinstance(anchors, list) else 0
    anchor_count = locator.get("anchor_count")
    if isinstance(anchor_count, int):
        return max(anchor_count, anchor_list_count, 0)
    return anchor_list_count


def _source_locator_has_anchor(locator: Optional[Dict[str, Any]]) -> bool:
    return _source_locator_anchor_count(locator) > 0


def _source_locator_has_bbox(locator: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(locator, dict):
        return False
    if locator.get("has_bbox"):
        return True
    anchors = locator.get("anchors") if isinstance(locator.get("anchors"), list) else []
    return any(isinstance(anchor, dict) and anchor.get("bbox") is not None for anchor in anchors)


def _source_locator_has_table_source(locator: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(locator, dict):
        return False
    if locator.get("has_table_source"):
        return True
    anchors = locator.get("anchors") if isinstance(locator.get("anchors"), list) else []
    return any(isinstance(anchor, dict) and anchor.get("type") == "table" for anchor in anchors)


def _source_locator_has_image_source(locator: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(locator, dict):
        return False
    if locator.get("has_image_source"):
        return True
    anchors = locator.get("anchors") if isinstance(locator.get("anchors"), list) else []
    return any(isinstance(anchor, dict) and anchor.get("type") == "image" for anchor in anchors)


def _normalize_artifact_type(value: Any) -> str:
    return str(value or "").strip().lower()


def _content_type_from_payload(payload: Dict[str, Any], artifact: Optional[Dict[str, Any]]) -> str:
    metadata = _metadata_from_payload(payload)
    return _normalize_artifact_type(
        metadata.get("content_type")
        or payload.get("content_type")
        or (artifact or {}).get("type")
    )


def _has_table_structure(artifact: Dict[str, Any]) -> bool:
    headers = artifact.get("headers")
    rows = artifact.get("rows")
    markdown = artifact.get("markdown")
    has_headers = isinstance(headers, list) and len(headers) > 0
    has_rows = isinstance(rows, list) and len(rows) > 0
    return bool(has_headers and (has_rows or markdown))


def _ocr_confidence_values(images: List[Any]) -> List[float]:
    values: List[float] = []
    for image in images:
        if not isinstance(image, dict):
            continue
        confidence = image.get("confidence")
        if isinstance(confidence, (int, float)):
            values.append(float(confidence))
    return values


def _optional_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _calc_recall_precision_at_k(hit_flags: List[bool], k: int) -> Tuple[float, float]:
    k = max(1, int(k))
    top = hit_flags[:k]
    hits = sum(1 for x in top if x)
    # recall: 是否命中任一 gold（针对“找证据”场景的最小可用定义）
    recall = 1.0 if hits > 0 else 0.0
    precision = hits / k
    return recall, precision


def _calc_mrr(hit_flags: List[bool]) -> float:
    for idx, hit in enumerate(hit_flags, start=1):
        if hit:
            return 1.0 / idx
    return 0.0


def _calc_ndcg_at_k(hit_flags: List[bool], k: int) -> float:
    top = hit_flags[: max(1, int(k))]
    dcg = 0.0
    for idx, hit in enumerate(top, start=1):
        if hit:
            dcg += 1.0 / math.log2(idx + 1)
    ideal_hits = sorted(hit_flags, reverse=True)[: max(1, int(k))]
    idcg = 0.0
    for idx, hit in enumerate(ideal_hits, start=1):
        if hit:
            idcg += 1.0 / math.log2(idx + 1)
    return dcg / idcg if idcg else 0.0


def _is_hit(result: Dict[str, Any], gold_doc: str, gold_indices: List[int]) -> bool:
    payload = result.get("payload", {}) or {}
    if payload.get("document_id") != gold_doc:
        return False
    idx = payload.get("chunk_index")
    if not isinstance(idx, int):
        return False
    return idx in set(gold_indices or [])


def results_to_evidence_items(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert raw retriever results into EvidenceItem-compatible dicts."""
    evidence: List[Dict[str, Any]] = []
    for idx, result in enumerate(results, start=1):
        payload = _result_payload(result)
        metadata = dict(_metadata_from_payload(payload))
        artifact = _artifact_from_payload(payload)
        if artifact and not isinstance(metadata.get("artifact"), dict):
            metadata["artifact"] = artifact
        source_locator = _source_locator_from_payload(payload)
        if source_locator and not isinstance(metadata.get("source_locator"), dict):
            metadata["source_locator"] = source_locator

        chunk_index = payload.get("chunk_index")
        score = result.get("score", result.get("combined_score", 0.0))
        try:
            score = float(score or 0.0)
        except Exception:
            score = 0.0

        section_path = metadata.get("section_path") or []
        if isinstance(section_path, str):
            section_path = [section_path]
        elif not isinstance(section_path, list):
            section_path = []

        page = _optional_int(metadata.get("page") or metadata.get("page_number") or metadata.get("page_start"))
        evidence.append(
            {
                "id": f"S{idx}",
                "text": str(payload.get("text") or ""),
                "document_id": payload.get("document_id"),
                "file_id": payload.get("file_id"),
                "conversation_id": payload.get("conversation_id"),
                "chunk_id": payload.get("chunk_id"),
                "chunk_index": chunk_index if isinstance(chunk_index, int) else None,
                "document_title": (
                    payload.get("document_title")
                    or payload.get("filename")
                    or payload.get("title")
                    or payload.get("document_id")
                ),
                "section_path": [str(item) for item in section_path],
                "page": page,
                "score": score,
                "retrieval_type": (
                    result.get("retrieval_type")
                    or payload.get("retrieval_type")
                    or metadata.get("retrieval_type")
                    or "vector"
                ),
                "metadata": metadata,
            }
        )
    return evidence


def build_artifact_diagnostics(
    results: List[Dict[str, Any]],
    gold_doc: Optional[str] = None,
    gold_indices: Optional[List[int]] = None,
    required_artifact_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Measure whether retrieved evidence keeps structured table/OCR artifacts."""
    gold_index_list = _as_int_list(gold_indices or [])
    gold_index_set = set(gold_index_list)
    required_types = {
        _normalize_artifact_type(item)
        for item in (required_artifact_types or [])
        if _normalize_artifact_type(item)
    }

    retrieved_count = len(results)
    gold_hit_count = 0
    gold_hit_artifact_count = 0
    gold_hit_source_locator_count = 0
    gold_found_indices = set()
    artifact_evidence_count = 0
    structured_evidence_count = 0
    structured_artifact_count = 0
    source_locator_count = 0
    structured_source_locator_count = 0
    missing_source_locator_count = 0
    structured_missing_source_locator_count = 0
    bbox_source_locator_count = 0
    table_source_locator_count = 0
    ocr_source_locator_count = 0
    source_anchor_count = 0
    table_artifact_count = 0
    table_artifact_complete_count = 0
    table_artifact_with_source_count = 0
    ocr_artifact_count = 0
    ocr_artifact_with_source_count = 0
    ocr_low_confidence_source_count = 0
    ocr_confidences: List[float] = []
    artifact_type_counts: Dict[str, int] = {}
    observed_artifact_types = set()

    for result in results:
        payload = _result_payload(result)
        metadata = _metadata_from_payload(payload)
        artifact = _artifact_from_payload(payload)
        source_locator = _source_locator_from_payload(payload)
        content_type = _content_type_from_payload(payload, artifact)
        artifact_type = _normalize_artifact_type((artifact or {}).get("type") or content_type)
        is_structured = content_type in STRUCTURED_ARTIFACT_TYPES or artifact_type in STRUCTURED_ARTIFACT_TYPES
        has_source_locator = _source_locator_has_anchor(source_locator)

        chunk_index = payload.get("chunk_index")
        is_gold_hit = (
            bool(gold_doc)
            and payload.get("document_id") == gold_doc
            and isinstance(chunk_index, int)
            and chunk_index in gold_index_set
        )
        if is_gold_hit:
            gold_hit_count += 1
            gold_found_indices.add(chunk_index)
            if has_source_locator:
                gold_hit_source_locator_count += 1

        if artifact:
            artifact_evidence_count += 1
            observed_artifact_types.add(artifact_type)
            artifact_type_counts[artifact_type] = artifact_type_counts.get(artifact_type, 0) + 1
            if is_gold_hit:
                gold_hit_artifact_count += 1

        if is_structured:
            structured_evidence_count += 1
            if artifact:
                structured_artifact_count += 1
            if has_source_locator:
                structured_source_locator_count += 1
            else:
                structured_missing_source_locator_count += 1

        if has_source_locator:
            source_locator_count += 1
            source_anchor_count += _source_locator_anchor_count(source_locator)
            if _source_locator_has_bbox(source_locator):
                bbox_source_locator_count += 1
            if _source_locator_has_table_source(source_locator):
                table_source_locator_count += 1
            if _source_locator_has_image_source(source_locator):
                ocr_source_locator_count += 1
        else:
            missing_source_locator_count += 1

        if artifact and artifact_type == "table":
            table_artifact_count += 1
            if _has_table_structure(artifact):
                table_artifact_complete_count += 1
            sources = artifact.get("sources")
            if isinstance(sources, list) and sources:
                table_artifact_with_source_count += 1

        if artifact and artifact_type in {"image_ocr", "ocr"}:
            ocr_artifact_count += 1
            images = artifact.get("images")
            images = images if isinstance(images, list) else []
            if images:
                ocr_artifact_with_source_count += 1
            ocr_low_confidence_source_count += sum(
                1 for image in images if isinstance(image, dict) and image.get("low_confidence") is True
            )
            ocr_confidences.extend(_ocr_confidence_values(images))

        if not artifact and metadata.get("artifact"):
            artifact_type_counts["invalid"] = artifact_type_counts.get("invalid", 0) + 1

    gold_missing_indices = sorted(gold_index_set - gold_found_indices)
    missing_required_types = sorted(required_types - observed_artifact_types)
    avg_ocr_confidence = round(sum(ocr_confidences) / len(ocr_confidences), 4) if ocr_confidences else None

    return {
        "retrieved_count": retrieved_count,
        "gold_count": len(gold_index_set),
        "gold_hit_count": gold_hit_count,
        "gold_found_count": len(gold_found_indices),
        "gold_found_chunk_indices": sorted(gold_found_indices),
        "gold_missing_chunk_indices": gold_missing_indices,
        "gold_coverage": _safe_ratio(len(gold_found_indices), len(gold_index_set)),
        "gold_hit_artifact_count": gold_hit_artifact_count,
        "gold_hit_artifact_coverage": _safe_ratio(gold_hit_artifact_count, gold_hit_count),
        "gold_hit_source_locator_count": gold_hit_source_locator_count,
        "gold_hit_source_locator_coverage": _safe_ratio(gold_hit_source_locator_count, gold_hit_count),
        "artifact_evidence_count": artifact_evidence_count,
        "artifact_coverage": _safe_ratio(artifact_evidence_count, retrieved_count),
        "structured_evidence_count": structured_evidence_count,
        "structured_artifact_count": structured_artifact_count,
        "structured_artifact_coverage": _safe_ratio(structured_artifact_count, structured_evidence_count),
        "source_locator_count": source_locator_count,
        "source_locator_coverage": _safe_ratio(source_locator_count, retrieved_count),
        "structured_source_locator_count": structured_source_locator_count,
        "structured_source_locator_coverage": _safe_ratio(structured_source_locator_count, structured_evidence_count),
        "missing_source_locator_count": missing_source_locator_count,
        "structured_missing_source_locator_count": structured_missing_source_locator_count,
        "bbox_source_locator_count": bbox_source_locator_count,
        "table_source_locator_count": table_source_locator_count,
        "ocr_source_locator_count": ocr_source_locator_count,
        "source_anchor_count": source_anchor_count,
        "artifact_type_counts": artifact_type_counts,
        "required_artifact_types": sorted(required_types),
        "missing_required_artifact_types": missing_required_types,
        "table_artifact_count": table_artifact_count,
        "table_artifact_complete_count": table_artifact_complete_count,
        "table_artifact_with_source_count": table_artifact_with_source_count,
        "ocr_artifact_count": ocr_artifact_count,
        "ocr_artifact_with_source_count": ocr_artifact_with_source_count,
        "ocr_low_confidence_source_count": ocr_low_confidence_source_count,
        "ocr_average_confidence": avg_ocr_confidence,
    }


def summarize_artifact_diagnostics(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not items:
        return {"evaluated_count": 0}

    count_fields = [
        "retrieved_count",
        "gold_count",
        "gold_hit_count",
        "gold_found_count",
        "gold_hit_artifact_count",
        "gold_hit_source_locator_count",
        "artifact_evidence_count",
        "structured_evidence_count",
        "structured_artifact_count",
        "source_locator_count",
        "structured_source_locator_count",
        "missing_source_locator_count",
        "structured_missing_source_locator_count",
        "bbox_source_locator_count",
        "table_source_locator_count",
        "ocr_source_locator_count",
        "source_anchor_count",
        "table_artifact_count",
        "table_artifact_complete_count",
        "table_artifact_with_source_count",
        "ocr_artifact_count",
        "ocr_artifact_with_source_count",
        "ocr_low_confidence_source_count",
    ]
    ratio_fields = [
        "gold_coverage",
        "gold_hit_artifact_coverage",
        "gold_hit_source_locator_coverage",
        "artifact_coverage",
        "structured_artifact_coverage",
        "source_locator_coverage",
        "structured_source_locator_coverage",
        "ocr_average_confidence",
    ]

    summary: Dict[str, Any] = {"evaluated_count": len(items)}
    for field in count_fields:
        summary[field] = sum(int(item.get(field) or 0) for item in items)

    for field in ratio_fields:
        values = [item.get(field) for item in items if isinstance(item.get(field), (int, float))]
        summary[f"avg_{field}"] = round(sum(values) / len(values), 4) if values else None

    type_counts: Dict[str, int] = {}
    missing_required = set()
    for item in items:
        for key, value in (item.get("artifact_type_counts") or {}).items():
            type_counts[key] = type_counts.get(key, 0) + int(value or 0)
        missing_required.update(item.get("missing_required_artifact_types") or [])
    summary["artifact_type_counts"] = type_counts
    summary["missing_required_artifact_types"] = sorted(missing_required)
    return summary


def _citation_quality_for_item(item: Dict[str, Any], results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    direct = item.get("citation_quality")
    if isinstance(direct, dict):
        return direct

    generated = item.get("generated")
    if isinstance(generated, dict):
        direct = generated.get("citation_quality")
        if isinstance(direct, dict):
            return direct
        answer = generated.get("answer") or generated.get("text")
    else:
        answer = None

    answer = item.get("answer") or item.get("generated_answer") or answer
    if not isinstance(answer, str) or not answer.strip():
        return None
    return build_citation_diagnostics(answer, results_to_evidence_items(results))


def summarize_citation_quality(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "evaluated_count": len(items),
        "status_counts": {},
        "risk_level_counts": {},
        "avg_coverage": None,
        "invalid_citation_count": 0,
        "duplicate_citation_count": 0,
        "cited_structured_evidence_count": 0,
        "cited_missing_source_locator_count": 0,
        "cited_artifact_warning_count": 0,
        "cited_low_confidence_ocr_count": 0,
        "warning_count": 0,
    }
    if not items:
        return summary

    coverage_values: List[float] = []
    for item in items:
        status = str(item.get("status") or "unknown")
        summary["status_counts"][status] = summary["status_counts"].get(status, 0) + 1
        risk_level = str(item.get("risk_level") or "unknown")
        summary["risk_level_counts"][risk_level] = summary["risk_level_counts"].get(risk_level, 0) + 1
        coverage = item.get("coverage")
        if isinstance(coverage, (int, float)):
            coverage_values.append(float(coverage))
        summary["invalid_citation_count"] += len(item.get("invalid_citation_ids") or [])
        summary["duplicate_citation_count"] += len(item.get("duplicate_citation_ids") or [])
        summary["cited_structured_evidence_count"] += int(item.get("cited_structured_evidence_count") or 0)
        summary["cited_missing_source_locator_count"] += len(item.get("cited_missing_source_locator_ids") or [])
        summary["cited_artifact_warning_count"] += len(item.get("cited_artifact_warning_ids") or [])
        summary["cited_low_confidence_ocr_count"] += len(item.get("cited_low_confidence_ocr_ids") or [])
        summary["warning_count"] += len(item.get("warnings") or [])
    if coverage_values:
        summary["avg_coverage"] = round(sum(coverage_values) / len(coverage_values), 4)
    return summary


async def eval_retrieval(
    dataset_path: str,
    collection_name: str,
    ks: List[int],
    prefetch_k: int = 200,
    score_threshold: float = 0.7,
) -> Dict[str, Any]:
    data = _load_dataset(dataset_path)
    retriever = RAGRetriever(final_k=max(ks), prefetch_k=prefetch_k, score_threshold=score_threshold)

    per_k = {k: {"recall_sum": 0.0, "precision_sum": 0.0} for k in ks}
    ndcg_sum = {k: 0.0 for k in ks}
    mrr_sum = 0.0
    citation_recall_sum = 0.0
    citation_precision_sum = 0.0
    artifact_diagnostics: List[Dict[str, Any]] = []
    citation_quality_items: List[Dict[str, Any]] = []
    item_summaries: List[Dict[str, Any]] = []
    total = 0

    for item in data:
        q = item["query"]
        gold = item.get("gold") or {}
        gold_doc = gold.get("document_id")
        gold_indices = gold.get("chunk_indices") or []
        if not gold_doc or not isinstance(gold_indices, list):
            continue

        try:
            results = await retriever.retrieve_async(q, document_id=gold_doc, collection_name=collection_name)
        except Exception as e:
            logger.warning(f"检索评测条目失败，按空结果计入 - id={item.get('id')}, error={e}")
            results = []
        hit_flags = [_is_hit(r, gold_doc, gold_indices) for r in results]
        required_artifact_types = (
            item.get("required_artifact_types")
            or gold.get("required_artifact_types")
            or []
        )
        artifact_quality = build_artifact_diagnostics(
            results,
            gold_doc=gold_doc,
            gold_indices=gold_indices,
            required_artifact_types=required_artifact_types,
        )
        artifact_diagnostics.append(artifact_quality)
        citation_quality = _citation_quality_for_item(item, results)
        if citation_quality:
            citation_quality_items.append(citation_quality)

        for k in ks:
            r, p = _calc_recall_precision_at_k(hit_flags, k)
            per_k[k]["recall_sum"] += r
            per_k[k]["precision_sum"] += p
            ndcg_sum[k] += _calc_ndcg_at_k(hit_flags, k)
        mrr_sum += _calc_mrr(hit_flags)
        max_k = max(ks)
        citation_r, citation_p = _calc_recall_precision_at_k(hit_flags, max_k)
        citation_recall_sum += citation_r
        citation_precision_sum += citation_p
        total += 1
        item_summaries.append(
            {
                "id": item.get("id"),
                "query": q,
                "retrieved_count": len(results),
                "gold": {"document_id": gold_doc, "chunk_indices": gold_indices},
                "artifact_quality": artifact_quality,
                "citation_quality": citation_quality,
            }
        )

    out = {
        "total": total,
        "ks": ks,
        "prefetch_k": prefetch_k,
        "score_threshold": score_threshold,
        "metrics": {},
        "items": item_summaries,
    }
    for k in ks:
        if total == 0:
            out["metrics"][str(k)] = {"recall_at_k": 0.0, "precision_at_k": 0.0}
        else:
            out["metrics"][str(k)] = {
                "recall_at_k": per_k[k]["recall_sum"] / total,
                "precision_at_k": per_k[k]["precision_sum"] / total,
                "ndcg_at_k": ndcg_sum[k] / total,
            }
    out["metrics"]["mrr"] = 0.0 if total == 0 else mrr_sum / total
    out["metrics"]["citation"] = {
        "citation_recall": 0.0 if total == 0 else citation_recall_sum / total,
        "citation_precision": 0.0 if total == 0 else citation_precision_sum / total,
    }
    out["metrics"]["artifact"] = summarize_artifact_diagnostics(artifact_diagnostics)
    out["metrics"]["citation_quality"] = summarize_citation_quality(citation_quality_items)
    return out


def _format_metric_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _to_markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# Retrieval Evaluation",
        "",
        f"- total: {result.get('total', 0)}",
        f"- prefetch_k: {result.get('prefetch_k')}",
        f"- score_threshold: {result.get('score_threshold')}",
        "",
        "| metric | value |",
        "| --- | ---: |",
    ]
    metrics = result.get("metrics", {})
    for k in result.get("ks", []):
        item = metrics.get(str(k), {})
        lines.append(f"| recall@{k} | {item.get('recall_at_k', 0):.4f} |")
        lines.append(f"| precision@{k} | {item.get('precision_at_k', 0):.4f} |")
        lines.append(f"| ndcg@{k} | {item.get('ndcg_at_k', 0):.4f} |")
    lines.append(f"| mrr | {metrics.get('mrr', 0):.4f} |")
    citation = metrics.get("citation", {})
    lines.append(f"| citation_recall | {citation.get('citation_recall', 0):.4f} |")
    lines.append(f"| citation_precision | {citation.get('citation_precision', 0):.4f} |")

    artifact = metrics.get("artifact", {})
    if artifact:
        lines.extend(["", "## Artifact Quality", "", "| metric | value |", "| --- | ---: |"])
        for key in [
            "evaluated_count",
            "avg_gold_coverage",
            "avg_gold_hit_artifact_coverage",
            "avg_gold_hit_source_locator_coverage",
            "avg_artifact_coverage",
            "avg_structured_artifact_coverage",
            "avg_source_locator_coverage",
            "avg_structured_source_locator_coverage",
            "artifact_evidence_count",
            "structured_evidence_count",
            "structured_artifact_count",
            "source_locator_count",
            "structured_source_locator_count",
            "structured_missing_source_locator_count",
            "bbox_source_locator_count",
            "table_source_locator_count",
            "ocr_source_locator_count",
            "source_anchor_count",
            "table_artifact_complete_count",
            "table_artifact_with_source_count",
            "ocr_artifact_with_source_count",
            "ocr_low_confidence_source_count",
            "avg_ocr_average_confidence",
            "missing_required_artifact_types",
        ]:
            lines.append(f"| {key} | {_format_metric_value(artifact.get(key))} |")

    citation_quality = metrics.get("citation_quality", {})
    if citation_quality and citation_quality.get("evaluated_count"):
        lines.extend(["", "## Citation Quality", "", "| metric | value |", "| --- | ---: |"])
        for key in [
            "evaluated_count",
            "status_counts",
            "risk_level_counts",
            "avg_coverage",
            "invalid_citation_count",
            "duplicate_citation_count",
            "cited_structured_evidence_count",
            "cited_missing_source_locator_count",
            "cited_artifact_warning_count",
            "cited_low_confidence_ocr_count",
            "warning_count",
        ]:
            lines.append(f"| {key} | {_format_metric_value(citation_quality.get(key))} |")
    return "\n".join(lines) + "\n"


async def main():
    logger.setLevel("INFO")
    dataset_path = os.getenv("RETRIEVAL_DATASET", "eval/retrieval_dataset.example.json")
    collection_name = os.getenv("RETRIEVAL_COLLECTION", "default_knowledge")
    ks = [int(x) for x in os.getenv("RETRIEVAL_KS", "5,10,20").split(",") if x.strip()]
    prefetch_k = int(os.getenv("RETRIEVAL_PREFETCH_K", "200"))
    score_threshold = float(os.getenv("RETRIEVAL_SCORE_THRESHOLD", "0.7"))

    result = await eval_retrieval(
        dataset_path=dataset_path,
        collection_name=collection_name,
        ks=ks,
        prefetch_k=prefetch_k,
        score_threshold=score_threshold,
    )

    out_path = os.getenv("RETRIEVAL_EVAL_OUT", "eval/retrieval_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已保存: {out_path}")

    md_out_path = os.getenv("RETRIEVAL_EVAL_MD_OUT", out_path.replace(".json", ".md"))
    with open(md_out_path, "w", encoding="utf-8") as f:
        f.write(_to_markdown(result))
    print(f"已保存: {md_out_path}")


if __name__ == "__main__":
    asyncio.run(main())
