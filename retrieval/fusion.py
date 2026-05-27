"""Pure retrieval result fusion helpers."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple


def merge_results_rrf(
    ranked_lists: List[Tuple[str, List[Dict[str, Any]], float]],
    rrf_k: float | None = None,
) -> List[Dict[str, Any]]:
    """Reciprocal Rank Fusion for heterogeneous retrieval result lists."""
    k = float(rrf_k if rrf_k is not None else os.getenv("RRF_K", "60"))
    result_dict: Dict[str, Dict[str, Any]] = {}

    for modality, results, weight in ranked_lists:
        for rank, res in enumerate(results or [], start=1):
            payload = res.get("payload") or {}
            key = str(payload.get("chunk_id") or res.get("id"))
            if not key:
                continue
            if key not in result_dict:
                copied = dict(res)
                copied["payload"] = dict(payload)
                copied["score"] = 0.0
                copied["combined_score"] = 0.0
                copied["retrieval_types"] = []
                copied["raw_scores"] = {}
                result_dict[key] = copied

            item = result_dict[key]
            item["score"] = float(item.get("score", 0.0) or 0.0) + weight / (k + rank)
            item["combined_score"] = item["score"]
            if modality not in item["retrieval_types"]:
                item["retrieval_types"].append(modality)
            item["payload"]["retrieval_type"] = "hybrid" if len(item["retrieval_types"]) > 1 else modality
            item["payload"]["retrieval_types"] = item["retrieval_types"]
            item["raw_scores"][modality] = res.get("score", 0.0)

    merged = list(result_dict.values())
    merged.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return merged
