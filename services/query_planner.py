"""Rule-based retrieval planning for RAG queries."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from models.rag import QueryPlan


def _truthy(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


class QueryPlanner:
    """Small, deterministic planner that can later be replaced by an LLM planner."""

    def build_plan(
        self,
        query: str,
        runtime_modules: Optional[Dict[str, Any]] = None,
        runtime_params: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> QueryPlan:
        q = (query or "").strip()
        runtime_modules = runtime_modules or {}
        runtime_params = runtime_params or {}

        is_compare = any(k in q for k in ("对比", "比较", "差异", "优缺点", "优劣", "分别", "各自", "相同点", "不同点"))
        is_list = any(k in q for k in ("有哪些", "列举", "总结", "概括", "要点", "关键点", "核心观点", "主要结论"))
        is_clause = any(k in q for k in ("依据", "条款", "规定", "标准", "口径", "定义", "范围", "假设", "条件"))
        is_risk = any(k in q for k in ("风险", "限制", "不足", "漏洞", "反例", "校验", "证据"))

        final_k = 12
        prefetch_k = 200
        intent = "general"
        if len(q) > 80 or is_compare or is_list:
            final_k = 20
            intent = "compare" if is_compare else "summary"
        if is_clause:
            prefetch_k = 260
            final_k = max(final_k, 16)
            intent = "clause"
        if is_risk and intent == "general":
            intent = "verification"

        rewrite_enabled = _truthy(runtime_modules.get("query_rewrite_enabled"), True)
        need_rewrite = rewrite_enabled and (len(q) > 80 or is_compare or is_list or is_clause)
        rewritten_queries = self._rewrite_queries(q, intent) if need_rewrite else [q]

        return QueryPlan(
            intent=intent,
            need_rewrite=need_rewrite,
            need_graph=_truthy(runtime_modules.get("kg_retrieve_enabled"), True),
            prefetch_k=prefetch_k,
            final_k=final_k,
            context_budget=int(runtime_params.get("context_budget") or os.getenv("RAG_CONTEXT_BUDGET", "30000")),
            filters=filters or {},
            rewritten_queries=rewritten_queries,
            fusion_strategy=str(runtime_params.get("retrieval_fusion_strategy") or os.getenv("RETRIEVAL_FUSION_STRATEGY", "rrf")),
        )

    def _rewrite_queries(self, query: str, intent: str) -> List[str]:
        variants = [query]
        if intent == "compare":
            variants.append(f"{query} 对比 差异 优缺点")
            variants.append(f"{query} 共同点 不同点 依据")
        elif intent == "clause":
            variants.append(f"{query} 定义 范围 条件 例外")
            variants.append(f"{query} 条款 规定 依据")
        elif intent == "summary":
            variants.append(f"{query} 要点 结论 证据")
            variants.append(f"{query} 核心观点 关键发现")
        elif intent == "verification":
            variants.append(f"{query} 证据 风险 限制")
        else:
            variants.append(f"{query} 相关证据")

        deduped: List[str] = []
        seen = set()
        for item in variants:
            normalized = " ".join(item.split())
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(normalized)
        return deduped[:3]


query_planner = QueryPlanner()
