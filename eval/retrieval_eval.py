import asyncio
import json
import math
import os
import sys
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.rag_retriever import RAGRetriever
from utils.logger import logger


def _load_dataset(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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

    out = {"total": total, "ks": ks, "prefetch_k": prefetch_k, "score_threshold": score_threshold, "metrics": {}}
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
    return out


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
