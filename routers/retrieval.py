"""检索服务路由"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from retrieval.rag_retriever import RAGRetriever
from services.query_analyzer import query_analyzer
import asyncio

router = APIRouter()

# 注意：检索器实例在每次请求时根据参数动态创建，不限制数量


class RetrievalRequest(BaseModel):
    """检索请求模型"""
    query: str
    document_id: Optional[str] = None
    top_k: Optional[int] = 5
    assistant_id: Optional[str] = None  # 助手ID
    knowledge_space_ids: Optional[List[str]] = None  # 可选：指定一个或多个知识空间
    conversation_id: Optional[str] = None  # 对话ID（如果提供，会同时检索对话专用向量空间）


class QueryAnalysisRequest(BaseModel):
    """查询分析请求模型"""
    query: str


class QueryAnalysisResponse(BaseModel):
    """查询分析响应模型"""
    need_retrieval: bool
    reason: str
    confidence: str = "medium"  # high, medium, low


class RetrievalResponse(BaseModel):
    """检索响应模型"""
    context: str
    sources: List[Dict[str, Any]]
    evidence: Optional[List[Dict[str, Any]]] = []
    query_plan: Optional[Dict[str, Any]] = {}
    trace: Optional[Dict[str, Any]] = {}
    retrieval_count: int
    recommended_resources: Optional[List[Dict[str, Any]]] = []


@router.post("/analyze", response_model=QueryAnalysisResponse)
async def analyze_query(
    request: QueryAnalysisRequest
):
    """
    分析查询，判断是否需要检索上下文
    
    根据用户问题智能判断是否需要从知识库检索相关信息
    """
    from utils.logger import logger
    logger.info(f"查询分析请求 - 查询: {request.query[:50]}...")
    
    try:
        # 运行时开关：可关闭模型查询分析（低配模式）
        try:
            from services.runtime_config import get_runtime_config

            runtime_cfg = await get_runtime_config()
            modules = runtime_cfg.get("modules") or {}
            if not bool(modules.get("query_analyze_enabled", True)):
                return QueryAnalysisResponse(
                    need_retrieval=True,
                    reason="已关闭查询分析模块，默认需要检索（安全策略）",
                    confidence="low",
                )
        except Exception:
            pass

        # 使用查询分析器判断（在线程池中执行同步方法）
        loop = asyncio.get_event_loop()
        analysis_result = await loop.run_in_executor(
            None,
            query_analyzer.analyze,
            request.query
        )
        
        logger.info(f"查询分析结果 - 需要检索: {analysis_result.get('need_retrieval')}, 理由: {analysis_result.get('reason')}")
        
        return QueryAnalysisResponse(
            need_retrieval=analysis_result.get("need_retrieval", True),
            reason=analysis_result.get("reason", "未提供理由"),
            confidence=analysis_result.get("confidence", "medium")
        )
    except Exception as e:
        logger.error(f"查询分析失败: {str(e)}", exc_info=True)
        # 分析失败时，默认需要检索（安全策略）
        return QueryAnalysisResponse(
            need_retrieval=True,
            reason=f"分析失败，默认需要检索: {str(e)}",
            confidence="low"
        )


@router.post("", response_model=RetrievalResponse)
async def retrieve_context(
    request: RetrievalRequest
):
    """
    RAG检索接口
    
    根据查询文本检索相关文档块
    需要用户登录认证
    """
    from utils.logger import logger
    logger.info(f"RAG检索请求 - 查询: {request.query[:50]}..., 文档ID: {request.document_id}, top_k: {request.top_k}, assistant_id: {request.assistant_id}, conversation_id: {request.conversation_id}")
    try:
        # 获取助手对应的集合名称
        collection_name = None
        if request.assistant_id:
            try:
                from database.mongodb import mongodb
                from bson import ObjectId
                assistant_collection = mongodb.get_collection("course_assistants")
                assistant_doc = await assistant_collection.find_one({"_id": ObjectId(request.assistant_id)})
                if assistant_doc:
                    collection_name = assistant_doc.get("collection_name")
            except Exception as e:
                logger.warning(f"获取助手集合名称失败: {str(e)}")
        
        # 检索相关文档块（使用较大的top_k值，不限制数量）
        # 使用RAG服务进行检索（包含文档和资源）
        # 如果提供了conversation_id，会同时检索对话专用向量空间和助手知识库
        from services.rag_service import rag_service
        retrieval_result = await rag_service.retrieve_context(
            request.query,
            request.document_id,
            request.assistant_id,
            collection_name,
            request.conversation_id,
            knowledge_space_ids=request.knowledge_space_ids,
        )
        
        logger.info(f"RAG检索成功 - 检索到 {len(retrieval_result.get('sources', []))} 个文档来源, {len(retrieval_result.get('recommended_resources', []))} 个推荐资源")
        return RetrievalResponse(
            context=retrieval_result.get("context", ""),
            sources=retrieval_result.get("sources", []),
            evidence=retrieval_result.get("evidence", []),
            query_plan=retrieval_result.get("query_plan", {}),
            trace=retrieval_result.get("trace", {}),
            retrieval_count=len(retrieval_result.get("sources", [])),
            recommended_resources=retrieval_result.get("recommended_resources", [])
        )
    except Exception as e:
        logger.error(f"RAG检索失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"检索失败: {str(e)}"
        )
