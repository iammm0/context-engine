
"""RAG检索服务"""
from typing import List, Dict, Any, Optional
import asyncio
import os
import math
import re
from database.mongodb import ChunkRepository, mongodb_client
from database.qdrant_client import qdrant_client
from database.neo4j_client import neo4j_client
from embedding.embedding_service import embedding_service
from retrieval.fusion import merge_results_rrf
from services.knowledge_extraction_service import knowledge_extraction_service
from utils.logger import logger
from utils.token_utils import truncate_to_tokens

def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "y", "on")

class RAGRetriever:
    """RAG检索器（混合检索：向量检索 + 关键词检索 + 图谱检索 + 重排）"""
    
    def __init__(
        self,
        final_k: int = 5,
        score_threshold: float = 0.5,
        prefetch_k: Optional[int] = None,
        enable_reranker: Optional[bool] = None,
        reranker_model: Optional[str] = None,
        reranker_device: Optional[str] = None,
        reranker_max_tokens: int = 512,
        fusion_strategy: str = "rrf",
    ):
        """
        初始化RAG检索器
        
        Args:
            final_k: 最终返回的检索结果数量（用于拼上下文）
            score_threshold: 相似度阈值
            prefetch_k: 向量检索候选池大小（用于重排/动态裁剪），默认按 final_k 放大
            enable_reranker: 是否启用重排（默认读取环境变量 ENABLE_RERANKER）
            reranker_model: CrossEncoder 模型名（默认读取环境变量 RERANKER_MODEL）
            reranker_device: cpu/cuda（默认读取环境变量 RERANKER_DEVICE）
            reranker_max_tokens: 送入 CrossEncoder 的文本最大 token（近似预算）
        """
        self.final_k = final_k
        self.prefetch_k = prefetch_k or max(50, final_k * 10)
        self.score_threshold = score_threshold
        self.chunk_repo = ChunkRepository(mongodb_client)
        self._reranker = None
        self.enable_reranker = _env_flag("ENABLE_RERANKER", "0") if enable_reranker is None else bool(enable_reranker)
        self.reranker_model = reranker_model or os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")
        self.reranker_device = reranker_device or os.getenv("RERANKER_DEVICE", "cpu")
        self.reranker_max_tokens = reranker_max_tokens
        self.fusion_strategy = (fusion_strategy or "rrf").lower()

    def _get_reranker(self):
        """延迟加载 CrossEncoder，避免导入阶段崩溃影响服务启动。"""
        if not self.enable_reranker:
            return None
        if self._reranker is not None:
            return self._reranker
        try:
            from sentence_transformers import CrossEncoder  # type: ignore

            self._reranker = CrossEncoder(self.reranker_model, device=self.reranker_device)
            logger.info(f"重排模型加载成功: {self.reranker_model} ({self.reranker_device})")
            return self._reranker
        except Exception as e:
            # 失败自动降级，避免反复尝试
            self.enable_reranker = False
            logger.warning(f"重排模型加载失败，已自动禁用重排: {e}")
            self._reranker = None
            return None

    def retrieve(self, query: str, document_id: Optional[str] = None, collection_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        同步检索方法（向后兼容，但不推荐用于新功能）
        注意：此方法无法使用异步的图谱检索和实体提取，会降级为基础检索。
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                 # 这是一个hack，如果在运行中的loop里调用同步方法，我们无法直接运行async
                 # 这里只能降级为仅使用向量+关键词检索
                 logger.warning("在运行中的循环中调用同步 retrieve，降级为基础检索")
                 return self._basic_retrieve(query, document_id, collection_name)
            else:
                 return loop.run_until_complete(self.retrieve_async(query, document_id, collection_name))
        except RuntimeError:
            return asyncio.run(self.retrieve_async(query, document_id, collection_name))

    async def retrieve_async(
        self,
        query: str,
        document_id: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedding_model: Optional[str] = None,
        query_variants: Optional[List[str]] = None,
        graph_enabled: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """
        异步检索相关文档块 (High-level RAG)
        
        Args:
            query: 查询文本
            document_id: 可选的文档ID过滤
            collection_name: 可选的集合名称（用于多助手支持）
            embedding_model: 可选的向量模型名称
        
        Returns:
            检索结果列表，包含文本、相似度分数、元数据等
        """
        # 运行时开关：决定是否启用图谱检索/重排等高耗模块
        try:
            from services.runtime_config import get_runtime_config

            runtime_cfg = await get_runtime_config()
            modules = runtime_cfg.get("modules") or {}
            if not bool(modules.get("rerank_enabled", True)):
                self.enable_reranker = False
        except Exception:
            modules = {}

        if graph_enabled is None:
            graph_enabled = bool(modules.get("kg_retrieve_enabled", True))

        # 1. 并行执行多种检索策略
        queries = [q for q in (query_variants or [query]) if q and q.strip()]
        if not queries:
            queries = [query]

        vector_tasks = [
            self._vector_search(q, document_id, collection_name, embedding_model)
            for q in queries
        ]
        keyword_tasks = [
            self._keyword_search(q, document_id)
            for q in queries
        ]
        tasks = [
            asyncio.gather(*vector_tasks),
            asyncio.gather(*keyword_tasks),
            (self._graph_search(query, document_id) if graph_enabled else asyncio.sleep(0, result=[])),
        ]
        
        results_list = await asyncio.gather(*tasks)
        vector_groups, keyword_groups, graph_results = results_list
        vector_results = self._flatten_ranked_groups(vector_groups)
        keyword_results = self._flatten_ranked_groups(keyword_groups)
        
        # 2. 混合检索结果（合并和初步去重）
        merged_results = self._merge_results(vector_results, keyword_results, graph_results)
        
        # 3. 重排 (Rerank)
        reranker = self._get_reranker()
        if reranker and merged_results:
            reranked_results = self._rerank(query, merged_results, reranker=reranker)
            # 在线动态裁剪 k：基于重排分数分布自适应（兼顾 recall/precision）
            k = self._dynamic_k_from_scores(reranked_results, default_k=self.final_k)
            return reranked_results[:k]
        
        # 4. 如果没有重排，直接返回按合并分数排序的结果
        return merged_results[: self.final_k]

    def _dynamic_k_from_scores(self, results: List[Dict[str, Any]], default_k: int) -> int:
        """
        在线动态调 k（仅在 reranker 启用时生效）。
        - 区分度高（top1 与 topN 差距大）：减小 k 提升 precision
        - 区分度低（分数接近）：增大 k 保留 recall
        """
        if not results:
            return int(default_k)
        scores = [float(r.get("score", 0.0) or 0.0) for r in results]
        k_min = int(os.getenv("DYNK_MIN", "8"))
        k_max = int(os.getenv("DYNK_MAX", str(max(default_k, 24))))

        # 默认 k
        k = int(default_k)

        # 仅在有足够候选时判断
        if len(scores) >= max(10, default_k):
            s1 = scores[0]
            s10 = scores[min(9, len(scores) - 1)]
            gap = s1 - s10

            # gap 大：强相关集中
            if gap >= float(os.getenv("DYNK_GAP_HIGH", "2.0")):
                k = max(k_min, min(k, 12))
            # gap 小：区分度差，需要更多证据
            elif gap <= float(os.getenv("DYNK_GAP_LOW", "0.6")):
                k = min(k_max, max(k, 24))

        return max(k_min, min(k_max, k))

    def _basic_retrieve(self, query: str, document_id: Optional[str] = None, collection_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """仅包含向量和关键词的基础检索"""
        vector_results = asyncio.run(self._vector_search(query, document_id, collection_name))
        keyword_results = asyncio.run(self._keyword_search(query, document_id))
        merged = self._merge_results(vector_results, keyword_results, [])
        return merged[: self.final_k]

    def _flatten_ranked_groups(self, groups: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Merge query-variant result groups while preserving the best rank per chunk."""
        merged: Dict[str, Dict[str, Any]] = {}
        for group in groups or []:
            for rank, item in enumerate(group or [], start=1):
                payload = item.get("payload") or {}
                key = payload.get("chunk_id") or item.get("id")
                if not key:
                    continue
                current = merged.get(str(key))
                score = float(item.get("score", 0.0) or 0.0)
                if current is None or score > float(current.get("score", 0.0) or 0.0):
                    copied = dict(item)
                    copied["_variant_rank"] = rank
                    merged[str(key)] = copied
        return sorted(merged.values(), key=lambda x: x.get("score", 0.0), reverse=True)

    async def _vector_search(self, query: str, document_id: Optional[str], collection_name: Optional[str], embedding_model: Optional[str] = None) -> List[Dict[str, Any]]:
        """向量检索"""
        try:
            def _search_sync() -> List[Dict[str, Any]]:
                query_vector = embedding_service.encode_single(query, model_name=embedding_model)

                filter_conditions = None
                if document_id:
                    filter_conditions = {"document_id": document_id}

                from database.qdrant_client import get_qdrant_client
                client = get_qdrant_client(collection_name) if collection_name else qdrant_client
                return client.search(
                    query_vector=query_vector,
                    limit=self.prefetch_k,
                    score_threshold=self.score_threshold,
                    filter_conditions=filter_conditions,
                    query_text=query
                )

            results = await asyncio.to_thread(_search_sync)
            return results
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []

    async def _keyword_search(self, query: str, document_id: Optional[str]) -> List[Dict[str, Any]]:
        """关键词检索"""
        try:
            chunks = []
            if document_id:
                chunks = self.chunk_repo.get_chunks_by_document(document_id)
            else:
                chunks = self._candidate_chunks_for_keyword(query, limit=int(os.getenv("BM25_CANDIDATE_LIMIT", "1200")))

            if not chunks:
                return []

            query_terms = self._tokenize(query)
            if not query_terms:
                return []

            avgdl = sum(len(self._tokenize(c.get("text", ""))) for c in chunks) / max(len(chunks), 1)
            doc_freq: Dict[str, int] = {}
            tokenized_chunks = []
            for chunk in chunks:
                terms = self._tokenize(chunk.get("text", ""))
                tokenized_chunks.append((chunk, terms))
                for term in set(terms):
                    doc_freq[term] = doc_freq.get(term, 0) + 1

            k1 = 1.5
            b = 0.75
            results = []
            total_docs = len(chunks)
            for chunk, terms in tokenized_chunks:
                if not terms:
                    continue
                term_counts: Dict[str, int] = {}
                for term in terms:
                    term_counts[term] = term_counts.get(term, 0) + 1
                dl = len(terms)
                score = 0.0
                for term in query_terms:
                    tf = term_counts.get(term, 0)
                    if tf <= 0:
                        continue
                    df = doc_freq.get(term, 0)
                    idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
                    denom = tf + k1 * (1 - b + b * dl / max(avgdl, 1))
                    score += idf * (tf * (k1 + 1)) / denom
                if score > 0:
                    results.append({
                        "id": str(chunk.get("_id")),
                        "score": score,
                        "payload": {
                            "chunk_id": str(chunk.get("_id")),
                            "document_id": chunk.get("document_id"),
                            "text": chunk.get("text"),
                            "chunk_index": chunk.get("chunk_index"),
                            "metadata": chunk.get("metadata", {})
                        }
                    })
            return sorted(results, key=lambda x: x["score"], reverse=True)[: self.prefetch_k]
        except Exception as e:
            logger.error(f"关键词检索失败: {e}")
            return []

    def _tokenize(self, text: str) -> List[str]:
        clean = (text or "").lower()
        try:
            import jieba  # type: ignore
            tokens = [t.strip() for t in jieba.cut(clean) if t.strip()]
        except Exception:
            tokens = re.findall(r"[\w\u4e00-\u9fff]+", clean)
        return [t for t in tokens if len(t) > 1 or re.match(r"[\u4e00-\u9fff]", t)]

    def _candidate_chunks_for_keyword(self, query: str, limit: int = 1200) -> List[Dict[str, Any]]:
        terms = self._tokenize(query)[:8]
        if not terms:
            return []
        try:
            regexes = [{"text": {"$regex": re.escape(term), "$options": "i"}} for term in terms]
            cursor = self.chunk_repo.collection.find({"$or": regexes}).limit(limit)
            return [{**chunk, "_id": str(chunk["_id"])} for chunk in cursor]
        except Exception as e:
            logger.warning(f"关键词候选块查询失败: {e}")
            return []

    async def _graph_search(self, query: str, document_id: Optional[str]) -> List[Dict[str, Any]]:
        """图谱检索"""
        try:
            # 1. 提取查询实体
            entities = await knowledge_extraction_service.extract_entities(query)
            if not entities:
                return []
            
            results = []
            if neo4j_client.driver is None:
                neo4j_client.connect()
                
            if neo4j_client.driver:
                for entity in entities:
                    cypher = (
                        f"MATCH (n {{name: $name}})-[r]->(m) "
                        f"RETURN n.name as head, type(r) as relation, m.name as tail, r.source_doc as doc_id, r.source_chunk as chunk_id LIMIT 10"
                    )
                    records = await asyncio.to_thread(neo4j_client.execute_query, cypher, {"name": entity})
                    
                    if records:
                        text_parts = []
                        chunk_ids = set()
                        doc_ids = set()
                        
                        for record in records:
                            head = record.get('head')
                            relation = record.get('relation')
                            tail = record.get('tail')
                            if head and relation and tail:
                                text_parts.append(f"{head} {relation} {tail}")
                            
                            if record.get('chunk_id'):
                                chunk_ids.add(record.get('chunk_id'))
                            if record.get('doc_id'):
                                doc_ids.add(record.get('doc_id'))
                        
                        if document_id and document_id not in doc_ids:
                            continue

                        for chunk_id in chunk_ids:
                            chunk = self.chunk_repo.get_chunk_by_id(str(chunk_id))
                            if not chunk:
                                continue
                            if document_id and chunk.get("document_id") != document_id:
                                continue
                            meta = (chunk.get("metadata") or {}).copy()
                            meta["graph_relations"] = text_parts
                            results.append({
                                "id": str(chunk.get("_id")),
                                "score": 0.75,
                                "payload": {
                                    "chunk_id": str(chunk.get("_id")),
                                    "document_id": chunk.get("document_id"),
                                    "text": chunk.get("text"),
                                    "chunk_index": chunk.get("chunk_index"),
                                    "metadata": meta,
                                    "retrieval_type": "graph",
                                    "entities": entities,
                                }
                            })

                        if text_parts and not chunk_ids:
                            combined_text = "Knowledge Graph Context:\n" + "\n".join(text_parts)
                            results.append({
                                "id": f"graph_{entity}",
                                "score": 0.35,
                                "payload": {
                                    "text": combined_text,
                                    "retrieval_type": "graph",
                                    "entities": entities,
                                    "metadata": {"graph_relations": text_parts},
                                }
                            })
            return results
        except Exception as e:
            logger.error(f"图谱检索失败: {e}")
            return []

    def _merge_results(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        graph_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """合并多种检索结果"""
        if self.fusion_strategy == "rrf":
            return self._merge_results_rrf(vector_results, keyword_results, graph_results)

        return self._merge_results_score_boost(vector_results, keyword_results, graph_results)

    def _merge_results_score_boost(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        graph_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Legacy score-boost merge."""
        result_dict = {}
        
        # 1. 向量结果 (Base)
        for res in vector_results:
            key = res["payload"].get("chunk_id") or res["id"]
            res["payload"]["retrieval_type"] = "vector"
            result_dict[key] = res
            
        # 2. 关键词结果 (Boost)
        for res in keyword_results:
            key = res["payload"].get("chunk_id") or res["id"]
            if key in result_dict:
                # Boost score
                result_dict[key]["score"] += res["score"] * 0.3
                result_dict[key]["payload"]["retrieval_type"] = "hybrid"
            else:
                res["payload"]["retrieval_type"] = "keyword"
                result_dict[key] = res
                
        # 3. 图谱结果 (Add)
        # 图谱结果通常不是原始 chunk，而是生成的知识文本
        for res in graph_results:
            key = res["id"]
            res["payload"]["retrieval_type"] = "graph"
            result_dict[key] = res
            
        merged = list(result_dict.values())
        merged.sort(key=lambda x: x["score"], reverse=True)
        return merged

    def _merge_results_rrf(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        graph_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Reciprocal Rank Fusion across vector, BM25, and graph retrieval."""
        lists = [
            ("vector", vector_results, 1.0),
            ("keyword", keyword_results, 0.8),
            ("graph", graph_results, 0.7),
        ]
        return merge_results_rrf(lists)

    def _rerank(self, query: str, results: List[Dict[str, Any]], reranker) -> List[Dict[str, Any]]:
        """使用 Cross-Encoder 重排"""
        if not reranker or not results:
            return results
            
        try:
            # 准备 pairs [query, doc_text]
            pairs = []
            for res in results:
                text = res["payload"].get("text", "")
                # 控制送入 CrossEncoder 的 token 预算，避免长 chunk 造成延迟/崩溃
                text = truncate_to_tokens(text, self.reranker_max_tokens)
                pairs.append([query, text])
            
            # 预测分数
            scores = reranker.predict(pairs)
            
            # 更新分数并排序
            for i, score in enumerate(scores):
                results[i]["score"] = float(score)
                # 归一化分数? BGE reranker 输出 logits，可能需要 sigmoid，但直接排序即可
                
            results.sort(key=lambda x: x["score"], reverse=True)
            return results
        except Exception as e:
            logger.error(f"重排失败: {e}")
            return results
