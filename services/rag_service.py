"""RAG服务核心逻辑"""
from typing import Dict, Any, Optional
import asyncio
import time
from utils.logger import logger
from utils.token_utils import estimate_tokens, truncate_to_tokens
from models.rag import EvidenceItem
from utils.citation import format_evidence_context
from utils.evidence_quality import annotate_evidence_artifact_quality, build_evidence_quality_diagnostics


class RAGService:
    """RAG服务封装（通过HTTP调用知识库服务）"""

    def _dynamic_retrieval_params(self, query: str) -> Dict[str, int]:
        """
        在线动态调参（粗粒度启发式）：
        - 行业报告允许更高延迟/大上下文，因此默认扩大 prefetch_k
        - 对对比/多约束类问题适当增大 final_k
        """
        q = (query or "").strip()
        q_len = len(q)
        is_compare = any(k in q for k in ("对比", "比较", "差异", "优缺点", "优劣", "分别", "各自", "相同点", "不同点"))
        is_list = any(k in q for k in ("有哪些", "列举", "总结", "概括", "要点", "关键点", "核心观点", "主要结论"))
        is_clause = any(k in q for k in ("依据", "条款", "规定", "标准", "口径", "定义", "范围", "假设", "条件"))

        prefetch_k = 200
        final_k = 12

        if q_len > 80 or is_compare or is_list:
            final_k = 20
        if is_clause:
            prefetch_k = 260
            final_k = max(final_k, 16)

        return {"prefetch_k": prefetch_k, "final_k": final_k}
    
    async def retrieve_context(
        self,
        query: str,
        document_id: Optional[str] = None,
        assistant_id: Optional[str] = None,
        collection_name: Optional[str] = None,
        conversation_id: Optional[str] = None,
        knowledge_space_ids: Optional[list[str]] = None,
        embedding_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        检索相关上下文（并行检索文档和资源）
        
        Args:
            query: 用户查询
            document_id: 可选的文档ID过滤
            assistant_id: 可选的助手ID（用于获取集合名称）
            collection_name: 可选的集合名称（如果提供则直接使用）
            conversation_id: 可选的对话ID（如果提供，会同时检索对话专用向量空间）
            embedding_model: 可选的向量模型名称
        
        Returns:
            包含上下文、来源信息和推荐资源的字典
        """
        from database.mongodb import mongodb
        trace: Dict[str, Any] = {"query": query, "started_at": int(time.time() * 1000)}
        # 运行时开关：决定是否启用图谱检索/重排等高耗模块
        try:
            from services.runtime_config import get_runtime_config

            runtime_cfg = await get_runtime_config()
            modules = runtime_cfg.get("modules") or {}
            params = runtime_cfg.get("params") or {}
            rerank_enabled = bool(modules.get("rerank_enabled", True))
        except Exception:
            modules = {}
            params = {}
            rerank_enabled = True

        from services.query_planner import query_planner
        plan = query_planner.build_plan(
            query,
            runtime_modules=modules,
            runtime_params=params,
            filters={
                "document_id": document_id,
                "assistant_id": assistant_id,
                "collection_name": collection_name,
                "knowledge_space_ids": knowledge_space_ids or [],
            },
        )
        trace["query_plan"] = plan.model_dump()
        # 解析需要检索的集合列表（知识空间优先）
        collection_names: list[str] = []
        if knowledge_space_ids:
            try:
                from bson import ObjectId
                spaces = mongodb.get_collection("knowledge_spaces")
                for sid in knowledge_space_ids:
                    try:
                        doc = await spaces.find_one({"_id": ObjectId(sid)})
                        if doc and doc.get("collection_name"):
                            collection_names.append(doc["collection_name"])
                    except Exception:
                        continue
            except Exception as e:
                logger.warning(f"获取知识空间集合名称失败: {str(e)}")

        # 兼容：如果没有知识空间选择，则按旧 assistant_id/collection_name
        if not collection_names:
            if assistant_id and not collection_name:
                try:
                    from bson import ObjectId
                    collection = mongodb.get_collection("course_assistants")
                    assistant_doc = await collection.find_one({"_id": ObjectId(assistant_id)})
                    if assistant_doc:
                        collection_name = assistant_doc.get("collection_name")
                except Exception as e:
                    logger.warning(f"获取助手集合名称失败: {str(e)}")
            collection_names = [collection_name or "default_knowledge"]
        
        # 并行检索文档和资源
        loop = asyncio.get_event_loop()
        
        # 文档检索任务（知识空间集合，可多集合并行）
        from retrieval.rag_retriever import RAGRetriever
        doc_retriever = RAGRetriever(
            final_k=plan.final_k,
            prefetch_k=plan.prefetch_k,
            score_threshold=0.7,
            enable_reranker=rerank_enabled,
            fusion_strategy=plan.fusion_strategy,
        )
        
        # 使用异步检索方法 (retrieve_async)
        doc_tasks = [
            doc_retriever.retrieve_async(
                query,
                document_id,
                cn,
                embedding_model=embedding_model,
                query_variants=plan.rewritten_queries,
                graph_enabled=plan.need_graph,
            )
            for cn in collection_names
        ]
        
        # 等待文档检索完成并合并
        results_list = await asyncio.gather(*doc_tasks) if doc_tasks else [[]]
        results = []
        for part in results_list:
            results.extend(part or [])
        trace["retrieval"] = {
            "collection_count": len(collection_names),
            "result_count": len(results),
            "fusion_strategy": plan.fusion_strategy,
            "rewritten_queries": plan.rewritten_queries,
        }
        logger.info(f"知识空间检索完成 - 集合数: {len(collection_names)}, 结果数: {len(results)}")
        logger.info(f"RAG检索完成 - 文档结果: {len(results)} 个")
        
        # 构建上下文和来源（包含文档信息）
        evidence_items: list[EvidenceItem] = []
        sources = []

        # 邻居扩展：对命中 chunk 拉取前后窗口补齐定义/条件/例外
        # 注意：图谱结果没有 chunk_index，不参与邻居扩展
        from database.mongodb import ChunkRepository, mongodb_client
        chunk_repo = ChunkRepository(mongodb_client)
        neighbor_window = int((0 or 1))
        seen_chunk_ids = set()
        expanded_evidence: list[EvidenceItem] = []
        
        # 获取所有涉及的文档ID和文件ID（对话附件兼容）
        document_ids = set()
        file_ids = set()
        for result in results:
            doc_id = result["payload"].get("document_id")
            if doc_id:
                document_ids.add(doc_id)
            # 对话附件使用 file_id
            file_id = result["payload"].get("file_id")
            if file_id:
                file_ids.add(file_id)
        
        # 批量查询文档信息
        document_info_map = {}
        if document_ids:
            try:
                from database.mongodb import mongodb_client, DocumentRepository
                # 确保 MongoDB 客户端已连接
                if mongodb_client.db is None:
                    mongodb_client.connect()
                doc_repo = DocumentRepository(mongodb_client)
                
                for doc_id in document_ids:
                    try:
                        doc = doc_repo.get_document(doc_id)
                        if doc:
                            # 使用实际文件名，如果没有标题则使用文档ID的一部分
                            doc_title = doc.get("title") or doc.get("file_path", "").split("/")[-1] or f"文档_{doc_id[:8]}"
                            document_info_map[doc_id] = {
                                "title": doc_title,
                                "file_type": doc.get("file_type", ""),
                                "status": doc.get("status", "")
                            }
                    except Exception as e:
                        logger.warning(f"获取文档信息失败 - 文档ID: {doc_id}, 错误: {str(e)}")
                        # 使用文档ID的一部分作为标题
                        document_info_map[doc_id] = {
                            "title": f"文档_{doc_id[:8]}",
                            "file_type": "",
                            "status": ""
                        }
            except Exception as e:
                logger.warning(f"批量查询文档信息失败: {str(e)}")
        
        # 用于去重相同文档：每个文档只保留最高分的chunk
        document_sources_map = {}  # {document_id: source_info}
        
        for result in results:
            text = result["payload"].get("text", "")
            if text:
                chunk_id = result["payload"].get("chunk_id")
                doc_id = result["payload"].get("document_id")
                chunk_index = result["payload"].get("chunk_index")
                metadata = result["payload"].get("metadata", {}) or {}
                file_id = result["payload"].get("file_id")
                conversation_id = result["payload"].get("conversation_id")
                score = result.get("score", 0) or result.get("combined_score", 0)
                doc_info = document_info_map.get(doc_id, {}) if doc_id else {}
                document_title = (
                    result["payload"].get("filename")
                    or doc_info.get("title")
                    or (f"文档_{doc_id[:8]}" if doc_id else None)
                    or "Knowledge Graph"
                )
                section_path = metadata.get("section_path") or []
                if isinstance(section_path, str):
                    section_path = [section_path]
                elif not isinstance(section_path, list):
                    section_path = []
                page = metadata.get("page") or metadata.get("page_number")
                try:
                    page = int(page) if page is not None else None
                except Exception:
                    page = None
                evidence_items.append(EvidenceItem(
                    id=f"S{len(evidence_items) + 1}",
                    text=text,
                    document_id=doc_id,
                    file_id=file_id,
                    conversation_id=conversation_id,
                    chunk_id=chunk_id,
                    chunk_index=chunk_index if isinstance(chunk_index, int) else None,
                    document_title=document_title,
                    section_path=[str(s) for s in section_path],
                    page=page,
                    score=float(score or 0.0),
                    retrieval_type=result.get("retrieval_type") or result["payload"].get("retrieval_type") or metadata.get("retrieval_type") or "vector",
                    metadata=metadata,
                ))

                # 邻居扩展（仅对普通文档 chunk 生效）
                if chunk_id and doc_id is not None and chunk_index is not None and isinstance(chunk_index, int):
                    if chunk_id not in seen_chunk_ids:
                        seen_chunk_ids.add(chunk_id)
                        try:
                            neighbors = chunk_repo.get_neighbor_chunks(doc_id, chunk_index, window=neighbor_window)
                            for nb in neighbors:
                                nb_id = nb.get("_id")
                                if nb_id and nb_id not in seen_chunk_ids:
                                    seen_chunk_ids.add(nb_id)
                                    nb_meta = nb.get("metadata") or {}
                                    nb_section_path = nb_meta.get("section_path") or []
                                    if isinstance(nb_section_path, str):
                                        nb_section_path = [nb_section_path]
                                    elif not isinstance(nb_section_path, list):
                                        nb_section_path = []
                                    expanded_evidence.append(EvidenceItem(
                                        id=f"S{len(evidence_items) + len(expanded_evidence) + 1}",
                                        text=nb.get("text", ""),
                                        document_id=doc_id,
                                        chunk_id=nb_id,
                                        chunk_index=nb.get("chunk_index") if isinstance(nb.get("chunk_index"), int) else None,
                                        document_title=document_title,
                                        section_path=[str(s) for s in nb_section_path],
                                        page=(
                                            int(nb_meta.get("page"))
                                            if nb_meta.get("page") is not None and str(nb_meta.get("page")).isdigit()
                                            else None
                                        ),
                                        score=float(score or 0.0),
                                        retrieval_type="neighbor",
                                        metadata=nb_meta,
                                    ))
                        except Exception:
                            pass
                
                # 判断是文档还是对话附件
                if file_id and conversation_id:
                    # 对话附件
                    filename = result["payload"].get("filename", f"附件_{file_id[:8]}")
                    source_key = f"conversation_{conversation_id}_{file_id}"
                    source_info = {
                        "chunk_id": result["payload"].get("chunk_id"),
                        "chunk_index": chunk_index if isinstance(chunk_index, int) else None,
                        "evidence_id": evidence_items[-1].id if evidence_items else None,
                        "file_id": file_id,
                        "conversation_id": conversation_id,
                        "score": score,
                        "retrieval_type": result.get("retrieval_type") or result["payload"].get("retrieval_type", "vector"),
                        "document_title": filename,
                        "file_type": result["payload"].get("metadata", {}).get("file_type", ""),
                        "page": page,
                        "page_start": metadata.get("page_start"),
                        "page_end": metadata.get("page_end"),
                        "content_type": metadata.get("content_type"),
                        "artifact": metadata.get("artifact"),
                        "source_locator": metadata.get("source_locator"),
                        "section_path": section_path,
                        "is_conversation_attachment": True
                    }
                else:
                    # 普通文档
                    doc_title = doc_info.get("title") or (f"文档_{doc_id[:8]}" if doc_id else document_title)
                    source_key = doc_id or result.get("id") or (evidence_items[-1].id if evidence_items else "unknown")
                    source_info = {
                        "chunk_id": result["payload"].get("chunk_id"),
                        "chunk_index": chunk_index if isinstance(chunk_index, int) else None,
                        "evidence_id": evidence_items[-1].id if evidence_items else None,
                        "document_id": doc_id,
                        "score": score,
                        "retrieval_type": result.get("retrieval_type") or result["payload"].get("retrieval_type", "vector"),
                        "document_title": doc_title,
                        "file_type": doc_info.get("file_type", ""),
                        "status": doc_info.get("status", ""),
                        "page": page,
                        "page_start": metadata.get("page_start"),
                        "page_end": metadata.get("page_end"),
                        "content_type": metadata.get("content_type"),
                        "artifact": metadata.get("artifact"),
                        "source_locator": metadata.get("source_locator"),
                        "section_path": section_path,
                        "is_conversation_attachment": False
                    }
                
                # 如果该来源还没有记录，或者当前chunk的分数更高，则更新
                if source_key not in document_sources_map or score > document_sources_map[source_key]["score"]:
                    document_sources_map[source_key] = source_info
        
        # 将去重后的来源转换为列表，并按分数排序
        sources = list(document_sources_map.values())
        sources.sort(key=lambda x: x["score"], reverse=True)

        # 拼接上下文：证据块 + 邻居补齐，并控制总 token 预算
        evidence_items.extend([e for e in expanded_evidence if e.text and e.text.strip()])
        # 重新编号，确保邻居扩展后编号连续
        for idx, item in enumerate(evidence_items, start=1):
            item.id = f"S{idx}"
        annotate_evidence_artifact_quality(evidence_items)
        evidence_quality = build_evidence_quality_diagnostics(evidence_items)
        max_context_tokens = int(plan.context_budget or 30_000)
        joined = format_evidence_context(evidence_items)
        if estimate_tokens(joined) > max_context_tokens:
            joined = truncate_to_tokens(joined, max_context_tokens)
        context = joined
        trace["context"] = {
            "evidence_count": len(evidence_items),
            "context_tokens_estimate": estimate_tokens(context),
            "context_budget": max_context_tokens,
            "evidence_quality_status": evidence_quality.get("status"),
            "structured_artifact_coverage": evidence_quality.get("structured_artifact_coverage"),
        }
        trace["finished_at"] = int(time.time() * 1000)
        
        return {
            "context": context,
            "sources": sources,
            "evidence": [item.model_dump() for item in evidence_items],
            "evidence_quality": evidence_quality,
            "query_plan": plan.model_dump(),
            "trace": trace,
            "recommended_resources": []
        }
    
    async def generate_response(
        self,
        query: str,
        document_id: Optional[str] = None,
        use_context: bool = True,
        fallback_on_error: bool = True,
        assistant_id: Optional[str] = None,
        collection_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成回复（包含RAG检索）
        
        Args:
            query: 用户查询
            document_id: 可选的文档ID过滤
            use_context: 是否使用RAG上下文
            fallback_on_error: 当检索失败时是否回退到不使用上下文（默认True）
            assistant_id: 可选的助手ID（用于获取集合名称）
            collection_name: 可选的集合名称（如果提供则直接使用）
        
        Returns:
            包含回复和来源信息的字典
        """
        context = None
        sources = []
        retrieval_result: Dict[str, Any] = {
            "recommended_resources": [],
            "evidence": [],
            "evidence_quality": {},
            "query_plan": {},
            "trace": {},
        }
        
        if use_context:
            try:
                retrieval_result = await self.retrieve_context(query, document_id, assistant_id, collection_name)
                context = retrieval_result["context"]
                sources = retrieval_result["sources"]
                logger.info(f"RAG检索成功 - 检索到 {len(sources)} 个来源")
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"RAG检索失败: {error_msg}")
                
                if fallback_on_error:
                    logger.info("回退到不使用上下文的模式继续处理")
                    # 返回空上下文，让服务继续运行
                    context = None
                    sources = []
                else:
                    # 如果不允许回退，重新抛出异常
                    raise
        
        return {
            "context": context,
            "sources": sources,
            "evidence": retrieval_result.get("evidence", []),
            "evidence_quality": retrieval_result.get("evidence_quality", {}),
            "query_plan": retrieval_result.get("query_plan", {}),
            "trace": retrieval_result.get("trace", {}),
            "recommended_resources": retrieval_result.get("recommended_resources", [])
        }


# 全局RAG服务实例
rag_service = RAGService()
