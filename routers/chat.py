"""对话历史管理路由"""
import json
import os
import uuid
import asyncio
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, status, UploadFile, File, BackgroundTasks, Form, Request, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database.mongodb import mongodb, require_mongodb
from models.rag import CitationQuality, EvidenceItem, EvidenceQuality, RecommendedResource, SourceInfo
from models.task import TaskDispatchInfo
from services.document_task_dispatcher import (
    DocumentTaskQueueError,
    enqueue_document_processing,
    store_document_task_dispatch,
)
from services.task_status import enrich_task_dispatch
from utils.logger import logger
from utils.timezone import beijing_now

router = APIRouter()


def _dump_model_list(items: Optional[List[Any]]) -> List[Dict[str, Any]]:
    if not items:
        return []
    return [item.model_dump(exclude_none=True) if isinstance(item, BaseModel) else item for item in items]


def _dump_model(item: Optional[Any]) -> Optional[Dict[str, Any]]:
    if item is None:
        return None
    return item.model_dump(exclude_none=True) if isinstance(item, BaseModel) else item


class ChatMessage(BaseModel):
    """聊天消息模型"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[datetime] = None
    sources: Optional[List[SourceInfo]] = None  # 检索到的文档来源
    evidence: Optional[List[EvidenceItem]] = None  # chunk级证据
    evidence_quality: Optional[EvidenceQuality] = None
    citation_warnings: Optional[List[str]] = None
    citation_quality: Optional[CitationQuality] = None
    recommended_resources: Optional[List[RecommendedResource]] = None  # 推荐的相关资源


class Conversation(BaseModel):
    """对话模型"""
    id: str
    user_id: Optional[str] = None  # 用户ID（认证后使用）
    title: str
    messages: List[ChatMessage]
    created_at: datetime
    updated_at: datetime


class ConversationCreate(BaseModel):
    """创建对话请求"""
    title: Optional[str] = None
    user_id: Optional[str] = None
    assistant_id: Optional[str] = None  # 助手ID


class ConversationUpdate(BaseModel):
    """更新对话请求"""
    title: Optional[str] = None


class MessageAdd(BaseModel):
    """添加消息请求"""
    role: str
    content: str
    sources: Optional[List[SourceInfo]] = None
    evidence: Optional[List[EvidenceItem]] = None
    evidence_quality: Optional[EvidenceQuality] = None
    citation_warnings: Optional[List[str]] = None
    citation_quality: Optional[CitationQuality] = None
    recommended_resources: Optional[List[RecommendedResource]] = None


class MessageUpdate(BaseModel):
    """更新消息请求"""
    content: str


class ChatRequest(BaseModel):
    """常规对话请求"""
    query: str
    assistant_id: Optional[str] = None
    knowledge_space_ids: Optional[List[str]] = None  # 发起增强检索前可选知识空间（可多选）
    conversation_id: Optional[str] = None
    enable_rag: bool = True  # 是否启用RAG检索
    mode: str = "normal"  # 模式：normal（普通模式）或 network（网络检索模式）
    generation_config: Optional[Dict[str, Any]] = None  # 模型配置：{"llm_model": "...", "embedding_model": "..."}


class DeepResearchRequest(BaseModel):
    """深度研究模式请求"""
    query: str
    assistant_id: Optional[str] = None
    knowledge_space_ids: Optional[List[str]] = None
    conversation_id: Optional[str] = None
    enabled_agents: Optional[List[str]] = None  # 启用的专家Agent列表
    generation_config: Optional[Dict[str, Any]] = None  # 模型配置：{"llm_model": "...", "embedding_model": "...", "sub_agent_config": {...}}


class DeepResearchEvaluateRequest(BaseModel):
    """深度研究价值评估请求"""
    query: str
    conversation_id: Optional[str] = None


class DeepResearchGateDecision(BaseModel):
    """是否值得进入深度研究流程"""
    should_deep_research: bool
    score: int
    threshold: int
    reasons: List[str]


class ModelInfo(BaseModel):
    """Available model metadata."""
    name: str
    size: Optional[int] = None
    digest: Optional[str] = None
    modified_at: Optional[str] = None


class ModelsResponse(BaseModel):
    """Available models response."""
    models: List[ModelInfo]


class ConversationSummaryResponse(BaseModel):
    """Conversation list item."""
    id: str
    user_id: Optional[str] = None
    title: str
    message_count: int
    assistant_id: Optional[str] = None
    title_task: Optional[TaskDispatchInfo] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ConversationListResponse(BaseModel):
    """Conversation list response."""
    conversations: List[ConversationSummaryResponse]
    total: int
    skip: int
    limit: int


class ConversationMessageResponse(BaseModel):
    """Conversation detail message item."""
    message_id: Optional[str] = None
    role: str
    content: str
    timestamp: Optional[str] = None
    sources: Optional[List[SourceInfo]] = None
    evidence: Optional[List[EvidenceItem]] = None
    evidence_quality: Optional[EvidenceQuality] = None
    citation_warnings: Optional[List[str]] = None
    citation_quality: Optional[CitationQuality] = None
    recommended_resources: Optional[List[RecommendedResource]] = None


class ConversationDetailResponse(BaseModel):
    """Conversation detail response."""
    id: str
    user_id: Optional[str] = None
    title: str
    assistant_id: Optional[str] = None
    title_task: Optional[TaskDispatchInfo] = None
    messages: List[ConversationMessageResponse]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ConversationCreateResponse(BaseModel):
    """Conversation creation response."""
    id: str
    title: str
    assistant_id: Optional[str] = None
    created_at: str
    updated_at: str


class ConversationUpdateResponse(BaseModel):
    """Conversation update response."""
    id: str
    title: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ActionResponse(BaseModel):
    """Generic success response."""
    success: bool
    message: str


class MessageActionResponse(ActionResponse):
    """Conversation message action response."""
    message_id: Optional[str] = None
    timestamp: Optional[str] = None


class RegenerateMessageResponse(ActionResponse):
    """Conversation regenerate action response."""
    message_id: str
    remaining_messages: int


def _evaluate_deep_research_value(query: str, threshold: int) -> DeepResearchGateDecision:
    text = (query or "").strip()
    if not text:
        return DeepResearchGateDecision(
            should_deep_research=False,
            score=0,
            threshold=threshold,
            reasons=["问题为空，建议先补充明确问题。"],
        )

    score = 0
    reasons: List[str] = []

    # 复杂度：是否包含多步/对比/系统设计等迹象
    complexity_kw = [
        "对比", "比较", "差异", "权衡", "tradeoff", "架构", "方案", "设计", "流程", "多步", "系统",
        "root cause", "排查", "优化", "评估", "策略", "选型", "benchmark",
    ]
    if any(k.lower() in text.lower() for k in complexity_kw):
        score += 25
        reasons.append("问题包含方案对比或系统性推理，复杂度较高。")

    # 不确定性：疑问与开放性提问更可能需要更深入分析
    q_count = text.count("?") + text.count("？")
    if q_count >= 2 or re.search(r"(为什么|如何|怎么|是否|可行性|风险|边界)", text):
        score += 20
        reasons.append("问题存在较强不确定性，需要更多证据支撑。")

    # 风险：高代价场景关键词
    high_risk_kw = [
        "生产", "线上", "合规", "隐私", "安全", "财务", "医疗", "法律", "发布", "事故", "SLA", "风控",
    ]
    if any(k.lower() in text.lower() for k in high_risk_kw):
        score += 30
        reasons.append("问题涉及高风险场景，错误代价较高。")

    # 收益：长问题通常上下文丰富，深度研究收益更高
    if len(text) >= 120:
        score += 15
        reasons.append("问题信息量较大，深度研究预期收益更高。")
    elif len(text) <= 25:
        score -= 15
        reasons.append("问题较短，通常可用常规模式快速回答。")

    # 成本约束：超短问题进一步抑制触发深度研究
    if len(text.split()) <= 4 and len(text) <= 18:
        score -= 10
        reasons.append("问题可快速回答，进入深度研究的成本收益比偏低。")

    score = max(0, min(100, score))
    should = score >= threshold
    if not reasons:
        reasons.append("未命中高复杂度或高风险特征，优先走常规模式。")

    return DeepResearchGateDecision(
        should_deep_research=should,
        score=score,
        threshold=threshold,
        reasons=reasons,
    )


@router.get("/models", response_model=ModelsResponse)
async def list_models():
    """获取可用模型列表"""
    try:
        from services.ollama_service import OllamaService
        service = OllamaService()
        models = await service.list_models()
        return {"models": models}
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deep-research/evaluate", response_model=DeepResearchGateDecision)
async def evaluate_deep_research(
    request: DeepResearchEvaluateRequest,
    _: None = Depends(require_mongodb),
):
    """在进入深度研究前，先做一次低成本价值评估。"""
    try:
        threshold = 60
        try:
            from services.runtime_config import get_runtime_config
            cfg = await get_runtime_config()
            raw = (cfg.get("params") or {}).get("deep_research_threshold", threshold)
            threshold = max(0, min(100, int(raw)))
        except Exception as e:
            logger.warning(f"读取 deep_research_threshold 失败，使用默认阈值 60: {e}")

        decision = _evaluate_deep_research_value(request.query, threshold)
        logger.info(
            f"深度研究价值评估完成 - score={decision.score} threshold={decision.threshold} "
            f"should={decision.should_deep_research}"
        )
        return decision
    except Exception as e:
        logger.error(f"深度研究价值评估失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"深度研究价值评估失败: {str(e)}",
        )


@router.post("/conversations", response_model=ConversationCreateResponse)
async def create_conversation(
    request: ConversationCreate,
    _: None = Depends(require_mongodb),
):
    """
    创建新对话
    """
    logger.info(f"创建对话请求 - 标题: {request.title}")
    try:
        conversation_id = str(uuid.uuid4())
        now = beijing_now()
        
        # 如果没有提供assistant_id，获取默认助手
        assistant_id = request.assistant_id
        if not assistant_id:
            try:
                assistant_collection = mongodb.get_collection("course_assistants")
                default_assistant = await assistant_collection.find_one({"is_default": True})
                if default_assistant:
                    assistant_id = str(default_assistant["_id"])
            except Exception as e:
                logger.warning(f"获取默认助手失败: {str(e)}")
        
        # 匿名模式：不关联用户
        conversation = {
            "_id": conversation_id,
            "user_id": None,
            "title": request.title or "新对话",
            "assistant_id": assistant_id,  # 关联助手ID
            "messages": [],
            "created_at": now,
            "updated_at": now
        }
        
        collection = mongodb.get_collection("conversations")
        await collection.insert_one(conversation)
        
        logger.info(f"创建对话成功 - 对话ID: {conversation_id}")
        
        return {
            "id": conversation_id,
            "title": conversation["title"],
            "assistant_id": assistant_id,
            "created_at": conversation["created_at"].isoformat(),
            "updated_at": conversation["updated_at"].isoformat()
        }
    except Exception as e:
        logger.error(f"创建对话失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"创建对话失败: {str(e)}"
        )


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    skip: int = 0,
    limit: int = 100,
    _: None = Depends(require_mongodb),
):
    """
    获取对话列表
    普通用户只能看到自己的对话，管理员可以看到所有对话
    """
    logger.info(f"获取对话列表请求 - skip: {skip}, limit: {limit}")
    try:
        collection = mongodb.get_collection("conversations")
        cursor = collection.find({}).sort("updated_at", -1).skip(skip).limit(limit)
        conversations = []
        
        async for doc in cursor:
            conversations.append({
                "id": str(doc["_id"]),
                "user_id": doc.get("user_id"),
                "title": doc.get("title", "未命名对话"),
                "message_count": len(doc.get("messages", [])),
                "assistant_id": doc.get("assistant_id"),
                "title_task": enrich_task_dispatch(doc.get("title_task")),
                "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
                "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None
            })
        
        total = await collection.count_documents({})
        
        logger.info(f"获取对话列表成功 - 数量: {len(conversations)}")
        
        return {
            "conversations": conversations,
            "total": total,
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        logger.error(f"获取对话列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"获取对话列表失败: {str(e)}"
        )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    _: None = Depends(require_mongodb),
):
    """
    获取对话详情（包含所有消息）
    普通用户只能访问自己的对话，管理员可以访问所有对话
    """
    logger.info(f"获取对话详情请求 - 对话ID: {conversation_id}")
    try:
        collection = mongodb.get_collection("conversations")
        
        doc = await collection.find_one({"_id": conversation_id})
        
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在"
            )
        
        messages = []
        for msg in doc.get("messages", []):
            messages.append({
                "message_id": msg.get("message_id"),  # 返回消息ID
                "role": msg.get("role"),
                "content": msg.get("content"),
                "timestamp": msg.get("timestamp").isoformat() if msg.get("timestamp") else None,
                "sources": msg.get("sources", []),
                "evidence": msg.get("evidence", []),
                "evidence_quality": msg.get("evidence_quality"),
                "citation_warnings": msg.get("citation_warnings", []),
                "citation_quality": msg.get("citation_quality"),
                "recommended_resources": msg.get("recommended_resources", [])
            })
        
        return {
            "id": str(doc["_id"]),
            "user_id": doc.get("user_id"),
            "title": doc.get("title", "未命名对话"),
            "assistant_id": doc.get("assistant_id"),
            "title_task": enrich_task_dispatch(doc.get("title_task")),
            "messages": messages,
            "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
            "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取对话详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"获取对话详情失败: {str(e)}"
        )


@router.post("/conversations/{conversation_id}/messages", response_model=MessageActionResponse)
async def add_message(
    conversation_id: str,
    message: MessageAdd,
    _: None = Depends(require_mongodb),
):
    """
    向对话添加消息（匿名模式）
    """
    logger.info(f"添加消息请求 - 对话ID: {conversation_id}, 角色: {message.role}, 内容长度: {len(message.content)}")
    try:
        collection = mongodb.get_collection("conversations")
        
        # 检查对话是否存在
        doc = await collection.find_one({"_id": conversation_id})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在"
            )
        
        msg_dict = {
            "message_id": str(uuid.uuid4()),  # 为消息添加唯一ID
            "role": message.role,
            "content": message.content,
            "timestamp": beijing_now(),
            "sources": _dump_model_list(message.sources),
            "evidence": _dump_model_list(message.evidence),
            "evidence_quality": _dump_model(message.evidence_quality),
            "citation_warnings": message.citation_warnings or [],
            "citation_quality": _dump_model(message.citation_quality),
            "recommended_resources": _dump_model_list(message.recommended_resources)
        }
        
        result = await collection.update_one(
            {"_id": conversation_id},
            {
                "$push": {"messages": msg_dict},
                "$set": {"updated_at": beijing_now()}
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在"
            )
        
        # 如果是助手回复，且对话标题还是默认标题，则自动生成标题
        if message.role == "assistant":
            updated_doc = await collection.find_one({"_id": conversation_id})
            if updated_doc:
                current_title = updated_doc.get("title", "")
                # 如果标题是默认标题（如"新对话"）或标题是用户消息的前30个字符，则生成新标题
                if current_title in ["新对话", "新对话..."] or len(current_title) <= 5:
                    try:
                        from tasks.chat_tasks import generate_conversation_title_task

                        queued = generate_conversation_title_task.delay(conversation_id, current_title)
                        await collection.update_one(
                            {"_id": conversation_id},
                            {"$set": {"title_task": {"backend": "celery", "task_id": queued.id}}},
                        )
                        logger.info(
                            "Conversation title generation queued in Celery - conversation_id=%s task_id=%s",
                            conversation_id,
                            queued.id,
                        )
                    except Exception as e:
                        failed_title_task = {
                            "backend": "celery",
                            "task_id": None,
                            "state": "FAILURE",
                            "ready": True,
                            "successful": False,
                            "error": str(e)[:500],
                        }
                        try:
                            await collection.update_one(
                                {"_id": conversation_id},
                                {"$set": {"title_task": failed_title_task}},
                            )
                        except Exception:
                            logger.warning(
                                "Failed to persist title task enqueue failure - conversation_id=%s",
                                conversation_id,
                                exc_info=True,
                            )
                        logger.warning(f"启动标题生成任务失败: {str(e)}")
        
        logger.info(f"添加消息成功 - 对话ID: {conversation_id}, 角色: {message.role}")
        
        return {
            "success": True,
            "message": "消息已添加",
            "message_id": msg_dict["message_id"],
            "timestamp": msg_dict["timestamp"].isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加消息失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"添加消息失败: {str(e)}"
        )


@router.put("/conversations/{conversation_id}", response_model=ConversationUpdateResponse)
async def update_conversation(
    conversation_id: str,
    request: ConversationUpdate,
    _: None = Depends(require_mongodb),
):
    """
    更新对话（目前仅支持更新标题，匿名模式）
    """
    logger.info(f"更新对话请求 - 对话ID: {conversation_id}, 新标题: {request.title}")
    try:
        collection = mongodb.get_collection("conversations")
        
        # 检查对话是否存在
        doc = await collection.find_one({"_id": conversation_id})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在"
            )
        
        # 构建更新字段
        update_fields = {"updated_at": datetime.now(timezone.utc)}
        if request.title is not None:
            update_fields["title"] = request.title
            update_fields["title_task"] = None
        
        # 更新对话
        result = await collection.update_one(
            {"_id": conversation_id},
            {"$set": update_fields}
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在"
            )
        
        # 获取更新后的对话
        updated_doc = await collection.find_one({"_id": conversation_id})
        
        logger.info(f"更新对话成功 - 对话ID: {conversation_id}")
        
        return {
            "id": str(updated_doc["_id"]),
            "title": updated_doc.get("title", "未命名对话"),
            "created_at": updated_doc.get("created_at").isoformat() if updated_doc.get("created_at") else None,
            "updated_at": updated_doc.get("updated_at").isoformat() if updated_doc.get("updated_at") else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新对话失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"更新对话失败: {str(e)}"
        )


@router.delete("/conversations/{conversation_id}", response_model=ActionResponse)
async def delete_conversation(
    conversation_id: str,
    _: None = Depends(require_mongodb),
):
    """
    删除对话（匿名模式）
    """
    logger.info(f"删除对话请求 - 对话ID: {conversation_id}")
    try:
        collection = mongodb.get_collection("conversations")
        
        # 检查对话是否存在
        doc = await collection.find_one({"_id": conversation_id})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在"
            )
        
        # 删除对话
        result = await collection.delete_one({"_id": conversation_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在"
            )
        
        logger.info(f"删除对话成功 - 对话ID: {conversation_id}")
        
        return {
            "success": True,
            "message": "对话已删除"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除对话失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"删除对话失败: {str(e)}"
        )


@router.put("/conversations/{conversation_id}/messages/{message_id}", response_model=MessageActionResponse)
async def update_message(
    conversation_id: str,
    message_id: str,
    request: MessageUpdate,
    _: None = Depends(require_mongodb),
):
    """
    编辑用户消息（匿名模式）
    只能编辑 role=\"user\" 的消息，不能编辑助手消息
    """
    logger.info(f"编辑消息请求 - 对话ID: {conversation_id}, 消息ID: {message_id}")
    try:
        collection = mongodb.get_collection("conversations")
        
        # 检查对话是否存在
        doc = await collection.find_one({"_id": conversation_id})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在"
            )
        
        # 查找要编辑的消息
        messages = doc.get("messages", [])
        message_index = None
        for i, msg in enumerate(messages):
            if msg.get("message_id") == message_id:
                message_index = i
                break
        
        if message_index is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="消息不存在"
            )
        
        # 只能编辑用户消息，不能编辑助手消息
        if messages[message_index].get("role") != "user":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只能编辑用户消息，不能编辑助手回复"
            )
        
        # 更新消息内容
        messages[message_index]["content"] = request.content
        messages[message_index]["timestamp"] = beijing_now()  # 更新编辑时间
        
        # 保存更新后的消息列表
        result = await collection.update_one(
            {"_id": conversation_id},
            {
                "$set": {
                    "messages": messages,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在"
            )
        
        logger.info(f"编辑消息成功 - 对话ID: {conversation_id}, 消息ID: {message_id}")
        
        return {
            "success": True,
            "message": "消息已更新",
            "message_id": message_id,
            "timestamp": messages[message_index]["timestamp"].isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"编辑消息失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"编辑消息失败: {str(e)}"
        )


@router.post("/conversations/{conversation_id}/messages/{message_id}/regenerate", response_model=RegenerateMessageResponse)
async def regenerate_response(
    conversation_id: str,
    message_id: str,
    _: None = Depends(require_mongodb),
):
    """
    重新生成回答（匿名模式）
    删除指定用户消息之后的所有消息（包括该消息对应的助手回复），然后重新生成回答
    """
    logger.info(f"重新生成回答请求 - 对话ID: {conversation_id}, 消息ID: {message_id}")
    try:
        collection = mongodb.get_collection("conversations")
        
        # 检查对话是否存在
        doc = await collection.find_one({"_id": conversation_id})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在"
            )
        
        # 查找要重新生成的消息
        messages = doc.get("messages", [])
        message_index = None
        for i, msg in enumerate(messages):
            if msg.get("message_id") == message_id:
                message_index = i
                break
        
        if message_index is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="消息不存在"
            )
        
        # 只能重新生成用户消息对应的回答
        if messages[message_index].get("role") != "user":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只能重新生成用户消息对应的回答"
            )
        
        # 删除该消息之后的所有消息（包括该消息对应的助手回复）
        # 保留该消息及之前的所有消息
        messages = messages[:message_index + 1]
        
        # 保存更新后的消息列表
        result = await collection.update_one(
            {"_id": conversation_id},
            {
                "$set": {
                    "messages": messages,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在"
            )
        
        logger.info(f"删除后续消息成功 - 对话ID: {conversation_id}, 消息ID: {message_id}, 保留消息数: {len(messages)}")
        
        return {
            "success": True,
            "message": "后续消息已删除，可以重新生成回答",
            "message_id": message_id,
            "remaining_messages": len(messages)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新生成回答失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"重新生成回答失败: {str(e)}"
        )


@router.post(
    "/",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-sent event stream with chat tokens and final retrieval metadata.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def chat(
    chat_request: ChatRequest,
    http_request: Request,
    _: None = Depends(require_mongodb),
) -> StreamingResponse:
    """
    常规对话（匿名模式）
    使用 PhysicsAssistantAgent 处理，支持 RAG 检索增强与来源返回。
    支持客户端断开连接检测，断开时自动停止流式输出
    """
    logger.info(f"对话请求 - 问题: {chat_request.query[:50]}...")
    
    try:
        # 纯RAG系统：使用 GeneralAssistantAgent 处理请求
        logger.info("✓ 使用GeneralAssistantAgent处理请求")
        from agents.general_assistant.general_assistant_agent import GeneralAssistantAgent
        
        model_name = None
        if chat_request.generation_config:
             model_name = chat_request.generation_config.get("llm_model")
        
        agent = GeneralAssistantAgent(model_name=model_name)
        
        # 获取对话历史（如果提供了conversation_id）
        conversation_history = None
        if chat_request.conversation_id:
            try:
                collection = mongodb.get_collection("conversations")
                doc = await collection.find_one({"_id": chat_request.conversation_id})
                if doc:
                    messages = doc.get("messages", [])
                    conversation_history = [
                        {"role": msg.get("role"), "content": msg.get("content")}
                        for msg in messages[-10:]  # 最近10轮对话
                    ]
            except Exception as e:
                logger.warning(f"获取对话历史失败: {e}")
        
        # 构建上下文
        context = {
            "assistant_id": chat_request.assistant_id,
            "knowledge_space_ids": chat_request.knowledge_space_ids,
            "conversation_id": chat_request.conversation_id,
            "enable_rag": chat_request.enable_rag,
            "conversation_history": conversation_history,
            "generation_config": chat_request.generation_config,
        }
        
        # 流式生成响应（支持客户端断开连接检测）
        async def generate_stream():
            client_disconnected = False
            yield_count = 0
            
            try:
                full_response = ""
                sources = []
                evidence = []
                evidence_quality = {}
                citation_warnings = []
                citation_quality = {}
                query_plan = {}
                rag_trace = {}
                recommended_resources = []
                # 记录使用的Agent类型
                agent_type = type(agent).__name__
                logger.info(f"开始执行Agent任务 - Agent类型: {agent_type}")
                
                async for result in agent.execute(
                    task=chat_request.query,
                    context=context,
                    stream=True
                ):
                    # 每 10 次 yield 检查一次连接状态（性能优化）
                    yield_count += 1
                    if yield_count % 10 == 0:
                        if await http_request.is_disconnected():
                            logger.info("检测到客户端断开连接")
                            client_disconnected = True
                            break
                    
                    try:
                        if result.get("type") == "chunk":
                            chunk = result.get("content", "")
                            full_response += chunk
                            # 发送文本chunk
                            data = json.dumps({"content": chunk}, ensure_ascii=False)
                            yield f"data: {data}\n\n"
                        
                        elif result.get("type") == "complete":
                            sources = result.get("sources", [])
                            evidence = result.get("evidence", [])
                            evidence_quality = result.get("evidence_quality", {})
                            citation_warnings = result.get("citation_warnings", [])
                            citation_quality = result.get("citation_quality", {})
                            query_plan = result.get("query_plan", {})
                            rag_trace = result.get("trace", {})
                            recommended_resources = result.get("recommended_resources", [])
                            data = json.dumps({
                                "done": True,
                                "sources": sources,
                                "evidence": evidence,
                                "evidence_quality": evidence_quality,
                                "citation_warnings": citation_warnings,
                                "citation_quality": citation_quality,
                                "query_plan": query_plan,
                                "trace": rag_trace,
                                "recommended_resources": recommended_resources
                            }, ensure_ascii=False)
                            yield f"data: {data}\n\n"
                        
                        elif result.get("type") == "error":
                            error_data = json.dumps({"error": result.get("content", "")}, ensure_ascii=False)
                            yield f"data: {error_data}\n\n"
                    
                    except (asyncio.CancelledError, BrokenPipeError, ConnectionResetError, OSError) as e:
                        # 客户端断开连接（正常情况）
                        logger.info(f"客户端断开连接，停止流式输出 - 错误类型: {type(e).__name__}")
                        client_disconnected = True
                        break
                
            except asyncio.CancelledError:
                # 任务被取消（通常是客户端断开）
                logger.info("流式生成任务被取消")
                client_disconnected = True
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                # 连接错误（客户端断开）
                logger.info(f"连接错误，客户端可能已断开 - 错误: {str(e)}")
                client_disconnected = True
            except Exception as e:
                # 真正的系统错误
                if not client_disconnected:
                    logger.error(f"流式生成失败: {e}", exc_info=True)
                    try:
                        error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
                        yield f"data: {error_data}\n\n"
                    except:
                        pass  # 如果此时客户端已断开，忽略
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    except Exception as e:
        logger.error(f"对话失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"对话失败: {str(e)}"
        )


@router.post(
    "/deep-research",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-sent event stream with deep research planning, agent status, and results.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def deep_research_chat(
    research_request: DeepResearchRequest,
    http_request: Request,
    _: None = Depends(require_mongodb),
) -> StreamingResponse:
    """
    深度研究模式
    
    使用协调型Agent和多个专家Agent协作生成深度研究结果
    返回HTML格式的响应
    支持客户端断开连接检测，断开时自动停止流式输出
    """
    logger.info(f"深度研究模式请求 - 问题: {research_request.query[:50]}...")
    
    try:
        from agents.workflow.agent_workflow import AgentWorkflow
        from agents.builder.response_builder import ResponseBuilder
        
        # 初始化工作流和构建器
        workflow = AgentWorkflow()
        builder = ResponseBuilder()
        
        # 获取对话历史（如果提供了conversation_id）
        conversation_history = None
        if research_request.conversation_id:
            try:
                collection = mongodb.get_collection("conversations")
                doc = await collection.find_one({"_id": research_request.conversation_id})
                if doc:
                    messages = doc.get("messages", [])
                    conversation_history = [
                        {"role": msg.get("role"), "content": msg.get("content")}
                        for msg in messages[-5:]  # 最近5轮对话
                    ]
            except Exception as e:
                logger.warning(f"获取对话历史失败: {e}")
        
        # 构建上下文
        context = {
            "assistant_id": research_request.assistant_id,
            "knowledge_space_ids": research_request.knowledge_space_ids,
            "conversation_id": research_request.conversation_id,
            "conversation_history": conversation_history,
            "generation_config": research_request.generation_config,
        }
        
        # 流式生成响应（支持客户端断开连接检测）
        async def generate_stream():
            client_disconnected = False
            yield_count = 0
            
            try:
                agent_results = []
                planning_content = ""
                
                # 执行工作流
                async for result in workflow.execute_workflow(
                    query=research_request.query,
                    context=context,
                    enabled_agents=research_request.enabled_agents,
                    stream=True
                ):
                    # 每 10 次 yield 检查一次连接状态（性能优化）
                    yield_count += 1
                    if yield_count % 10 == 0:
                        if await http_request.is_disconnected():
                            logger.info("检测到客户端断开连接")
                            client_disconnected = True
                            break
                    
                    try:
                        if result.get("type") == "planning":
                            planning_content = result.get("content", "")
                            # 发送规划结果
                            data = json.dumps({
                                "type": "planning",
                                "run_id": result.get("run_id"),
                                "content": planning_content,
                                "selected_agents": result.get("selected_agents", []),
                                "agent_tasks": result.get("agent_tasks", {}),
                                "dependencies": result.get("dependencies", {}),
                                "parallel_groups": result.get("parallel_groups", []),
                                "reasoning": result.get("reasoning", "")
                            }, ensure_ascii=False)
                            yield f"data: {data}\n\n"
                        
                        elif result.get("type") == "agent_result":
                            # 发送单个Agent的结果
                            agent_results.append({
                                "agent_type": result.get("agent_type"),
                                "content": result.get("content", ""),
                                "sources": result.get("sources", []),
                                "confidence": result.get("confidence", 0.5)
                            })
                            data = json.dumps({
                                "type": "agent_result",
                                "run_id": result.get("run_id"),
                                "agent_type": result.get("agent_type"),
                                "content": result.get("content", ""),
                                "sources": result.get("sources", []),
                                "evidence": result.get("evidence", []),
                                "evidence_ids": result.get("evidence_ids", []),
                                "claims": result.get("claims", []),
                                "open_questions": result.get("open_questions", []),
                                "confidence": result.get("confidence", 0.5),
                                "dependencies": result.get("dependencies", []),
                            }, ensure_ascii=False)
                            yield f"data: {data}\n\n"

                        elif result.get("type") == "agent_status":
                            data = json.dumps({
                                "type": "agent_status",
                                "run_id": result.get("run_id"),
                                "agent_type": result.get("agent_type"),
                                "status": result.get("status"),
                                "current_step": result.get("current_step"),
                                "progress": result.get("progress"),
                                "details": result.get("details"),
                                "dependencies": result.get("dependencies", []),
                                "started_at": result.get("started_at"),
                                "completed_at": result.get("completed_at"),
                            }, ensure_ascii=False)
                            yield f"data: {data}\n\n"
                        
                        elif result.get("type") == "complete":
                            # 所有Agent执行完成，构建HTML响应
                            agent_results = result.get("agent_results", [])
                            
                            # 构建HTML
                            html_response = builder.build_html_response(
                                agent_results=agent_results,
                                query=research_request.query,
                                metadata={"planning": planning_content}
                            )
                            
                            # 发送HTML响应
                            data = json.dumps({
                                "type": "html",
                                "run_id": result.get("run_id"),
                                "content": html_response,
                                "selected_agents": result.get("selected_agents", []),
                                "dependencies": result.get("dependencies", {}),
                                "artifact": result.get("artifact", {}),
                            }, ensure_ascii=False)
                            yield f"data: {data}\n\n"
                            
                            # 发送完成标记
                            yield f"data: {json.dumps({'done': True, 'run_id': result.get('run_id'), 'artifact': result.get('artifact', {})}, ensure_ascii=False)}\n\n"
                        
                        elif result.get("type") == "error":
                            error_data = json.dumps({"error": result.get("content", "")}, ensure_ascii=False)
                            yield f"data: {error_data}\n\n"
                    
                    except (asyncio.CancelledError, BrokenPipeError, ConnectionResetError, OSError) as e:
                        # 客户端断开连接（正常情况）
                        logger.info(f"客户端断开连接，停止流式输出 - 错误类型: {type(e).__name__}")
                        client_disconnected = True
                        break
                
            except asyncio.CancelledError:
                # 任务被取消（通常是客户端断开）
                logger.info("流式生成任务被取消")
                client_disconnected = True
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                # 连接错误（客户端断开）
                logger.info(f"连接错误，客户端可能已断开 - 错误: {str(e)}")
                client_disconnected = True
            except Exception as e:
                # 真正的系统错误
                if not client_disconnected:
                    logger.error(f"深度研究模式流式生成失败: {e}", exc_info=True)
                    try:
                        error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
                        yield f"data: {error_data}\n\n"
                    except:
                        pass  # 如果此时客户端已断开，忽略
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    except Exception as e:
        logger.error(f"深度研究模式失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"深度研究模式失败: {str(e)}"
        )


@router.post("/deep-research/task", response_model=TaskDispatchInfo, status_code=status.HTTP_202_ACCEPTED)
async def queue_deep_research_task(
    research_request: DeepResearchRequest,
    _: None = Depends(require_mongodb),
) -> TaskDispatchInfo:
    """Queue deep research in Celery for clients that can consume task SSE."""

    try:
        from tasks.deep_research_tasks import deep_research_task

        queued = deep_research_task.delay(
            research_request.query,
            research_request.assistant_id,
            research_request.knowledge_space_ids,
            research_request.conversation_id,
            research_request.enabled_agents,
            research_request.generation_config,
        )
        logger.info(
            "Deep research queued in Celery - conversation_id=%s task_id=%s query=%s",
            research_request.conversation_id,
            queued.id,
            research_request.query[:80],
        )
        return TaskDispatchInfo(backend="celery", task_id=queued.id)
    except Exception as e:
        logger.error(f"投递深度研究任务失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"投递深度研究任务失败: {str(e)}",
        )


# 对话附件上传目录
CONVERSATION_UPLOAD_DIR = os.getenv("CONVERSATION_UPLOAD_DIR", "./conversation_uploads")
os.makedirs(CONVERSATION_UPLOAD_DIR, exist_ok=True)


class ConversationAttachmentStatus(BaseModel):
    """对话附件状态模型"""
    file_id: str
    conversation_id: str
    document_id: Optional[str] = None
    filename: str
    status: str  # uploading, processing, parsing, chunking, embedding, completed, failed
    progress_percentage: Optional[int] = 0
    current_stage: Optional[str] = None
    stage_details: Optional[str] = None
    message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    task: Optional[TaskDispatchInfo] = None


class ConversationAttachmentUploadResponse(BaseModel):
    """Conversation attachment upload response with queued task metadata."""
    file_id: str
    document_id: str
    status: str
    message: str
    task: TaskDispatchInfo


TERMINAL_ATTACHMENT_STATUSES = {"completed", "failed", "cancelled"}


async def _build_conversation_attachment_status_payload(
    conversation_id: str,
    file_id: str,
) -> ConversationAttachmentStatus:
    """Build attachment progress from the attachment record plus linked document status."""

    collection = mongodb.get_collection("conversations")
    conversation = await collection.find_one({"_id": conversation_id})

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话不存在"
        )

    attachment_collection = mongodb.get_collection("conversation_attachments")
    attachment = await attachment_collection.find_one({
        "conversation_id": conversation_id,
        "file_id": file_id
    })

    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="附件不存在"
        )

    doc_status = attachment.get("status", "unknown")
    progress_percentage = attachment.get("progress_percentage", 0)
    current_stage = attachment.get("current_stage")
    stage_details = attachment.get("stage_details")
    message = attachment.get("message")
    task = attachment.get("task")

    document_id = attachment.get("document_id")
    if document_id:
        try:
            from database.mongodb import DocumentRepository, mongodb_client
            if mongodb_client.db is None:
                mongodb_client.connect()
            repo = DocumentRepository(mongodb_client)
            doc = repo.get_document(document_id)
            if doc:
                doc_status = doc.get("status", doc_status)
                progress_percentage = doc.get("progress_percentage", progress_percentage)
                current_stage = doc.get("current_stage", current_stage)
                stage_details = doc.get("stage_details", stage_details)
                metadata = doc.get("metadata") or {}
                task = task or metadata.get("task")
                if doc_status == "completed":
                    message = "文件处理完成：已上传到目标知识空间，可用于增强检索。"
                elif doc_status == "failed":
                    message = message or doc.get("message") or stage_details or "文件处理失败"
        except Exception as e:
            logger.warning(f"读取文档进度失败: {e}")

    return ConversationAttachmentStatus(
        file_id=attachment.get("file_id"),
        conversation_id=attachment.get("conversation_id"),
        document_id=document_id,
        filename=attachment.get("filename"),
        status=doc_status,
        progress_percentage=progress_percentage,
        current_stage=current_stage,
        stage_details=stage_details,
        message=message,
        created_at=attachment.get("created_at").isoformat() if attachment.get("created_at") else None,
        updated_at=attachment.get("updated_at").isoformat() if attachment.get("updated_at") else None,
        task=enrich_task_dispatch(task),
    )


async def _update_attachment_status(
    conversation_id: str,
    file_id: str,
    status: str,
    progress_percentage: Optional[int] = None,
    current_stage: Optional[str] = None,
    stage_details: Optional[str] = None,
    message: Optional[str] = None
):
    """更新附件处理状态"""
    try:
        if mongodb.db is None:
            await mongodb.ensure_connected()
        collection = mongodb.get_collection("conversation_attachments")
        update_data = {
            "status": status,
            "updated_at": beijing_now()
        }
        if progress_percentage is not None:
            update_data["progress_percentage"] = progress_percentage
        if current_stage is not None:
            update_data["current_stage"] = current_stage
        if stage_details is not None:
            update_data["stage_details"] = stage_details
        if message is not None:
            update_data["message"] = message
        
        await collection.update_one(
            {"conversation_id": conversation_id, "file_id": file_id},
            {"$set": update_data},
            upsert=True
        )
    except Exception as e:
        logger.error(f"更新附件状态失败: {e}", exc_info=True)


@router.post("/conversation-attachment", response_model=ConversationAttachmentUploadResponse)
async def upload_conversation_attachment(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    conversation_id: str = Form(...),
    knowledge_space_id: str = Form(...),
    _: None = Depends(require_mongodb),
):
    """
    上传对话附件
    
    对话框附件上传（与知识库上传共通）：
    - 上传前必须选择目标知识空间
    - 复用知识库入库的解析/分块/向量化流水线
    """
    if not knowledge_space_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="knowledge_space_id 参数不能为空"
        )
    if not conversation_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="conversation_id 参数不能为空"
        )
    
    # 验证对话是否存在
    collection = mongodb.get_collection("conversations")
    conversation = await collection.find_one({"_id": conversation_id})
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话不存在"
        )
    
    # 检查文件名
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件名不能为空"
        )
    
    logger.info(f"对话附件上传请求 - 对话ID: {conversation_id}, 文件名: {file.filename}")
    
    # 检查文件类型
    allowed_extensions = {
        ".pdf", ".docx", ".doc", ".md", ".txt", ".markdown",
        ".pptx", ".xlsx", ".xls", ".html", ".htm",
        ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif",
    }
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型: {file_ext}。支持的类型: PDF, Word (.doc/.docx), Markdown, TXT, PowerPoint (.pptx), Excel (.xlsx/.xls), HTML, 图片 (.jpg/.png/.bmp/.webp/.tiff)"
        )
    
    # 生成文件ID
    file_id = str(uuid.uuid4())
    # 保存文件
    file_path = os.path.join(CONVERSATION_UPLOAD_DIR, f"{conversation_id}_{file_id}{file_ext}")
    
    try:
        # 读取文件内容
        file_content = await file.read()
        file_size = len(file_content)
        
        MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"文件大小不能超过200MB，当前文件大小: {file_size / (1024 * 1024):.2f}MB"
            )
        
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件不能为空"
            )
        
        # 保存文件
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
        
        # 先创建“文档”记录，复用知识库入库后台处理
        import hashlib
        file_hash = hashlib.sha256(file_content).hexdigest()

        from database.mongodb import DocumentRepository, mongodb_client
        if mongodb_client.db is None:
            mongodb_client.connect()
        doc_repo = DocumentRepository(mongodb_client)
        document_id = doc_repo.create_document(
            title=file.filename,
            file_type=file_ext[1:],
            file_path=file_path,
            file_size=file_size,
            file_hash=file_hash,
            assistant_id=None,
            knowledge_space_id=knowledge_space_id,
        )

        # 创建附件记录（关联 document_id）
        attachment_collection = mongodb.get_collection("conversation_attachments")
        attachment_doc = {
            "file_id": file_id,
            "conversation_id": conversation_id,
            "document_id": document_id,
            "knowledge_space_id": knowledge_space_id,
            "filename": file.filename,
            "file_path": file_path,
            "file_size": file_size,
            "file_type": file_ext[1:],
            "status": "uploading",
            "progress_percentage": 0,
            "created_at": beijing_now(),
            "updated_at": beijing_now()
        }
        await attachment_collection.insert_one(attachment_doc)
        
        # 更新状态：处理中
        await _update_attachment_status(
            conversation_id, file_id,
            status="processing",
            progress_percentage=5,
            current_stage="准备处理",
            stage_details="文件上传完成，准备处理..."
        )
        
        # 在后台异步处理文件（复用 documents 的后台入库）
        task_dispatch = enqueue_document_processing(
            background_tasks,
            file_path,
            document_id,
            None,
            knowledge_space_id,
        )
        store_document_task_dispatch(doc_repo, document_id, task_dispatch)
        try:
            await attachment_collection.update_one(
                {"conversation_id": conversation_id, "file_id": file_id},
                {"$set": {"task": task_dispatch, "updated_at": beijing_now()}},
            )
        except Exception:
            logger.warning(
                "Failed to persist conversation attachment task metadata - conversation_id=%s file_id=%s task=%s",
                conversation_id,
                file_id,
                task_dispatch,
                exc_info=True,
            )
        
        logger.info(f"对话附件上传成功，已启动后台处理任务 - 对话ID: {conversation_id}, 文件ID: {file_id}")
        
        return {
            "file_id": file_id,
            "document_id": document_id,
            "status": "processing",
            "message": "文件上传成功，正在后台处理",
            "task": task_dispatch,
        }
        
    except HTTPException:
        raise
    except DocumentTaskQueueError as e:
        if "doc_repo" in locals() and "document_id" in locals():
            try:
                doc_repo.update_document_status(document_id, "failed")
                doc_repo.update_document_progress(
                    document_id,
                    0,
                    "任务投递失败",
                    f"Celery 文档处理任务投递失败: {e}",
                )
            except Exception:
                logger.warning(
                    "Failed to mark attachment document queue dispatch failure - document_id=%s",
                    document_id,
                    exc_info=True,
                )
        await _update_attachment_status(
            conversation_id,
            file_id,
            status="failed",
            progress_percentage=0,
            current_stage="任务投递失败",
            stage_details=f"Celery 文档处理任务投递失败: {e}",
            message="文件上传成功，但文档处理任务投递失败",
        )
        logger.error(
            "对话附件文档处理任务投递失败 - conversation_id=%s file_id=%s error=%s",
            conversation_id,
            file_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"文档处理任务投递失败: {str(e)}",
        ) from e
    except Exception as e:
        # 清理文件
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        
        logger.error(f"对话附件上传失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件上传失败: {str(e)}"
        )


@router.get("/conversation-attachment/{conversation_id}/{file_id}/status", response_model=ConversationAttachmentStatus)
async def get_conversation_attachment_status(
    conversation_id: str,
    file_id: str,
    _: None = Depends(require_mongodb),
):
    """
    获取对话附件的处理状态
    
    实时返回处理进度和状态（包括上传中、解析中、分块中、向量化中、已完成等阶段）
    """
    return await _build_conversation_attachment_status_payload(conversation_id, file_id)


@router.get(
    "/conversation-attachment/{conversation_id}/{file_id}/status/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-sent event stream with attachment progress updates.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def stream_conversation_attachment_status(
    conversation_id: str,
    file_id: str,
    request: Request,
    interval: float = Query(1.5, ge=0.5, le=10.0),
    _: None = Depends(require_mongodb),
):
    """Stream conversation attachment processing progress as server-sent events."""

    async def event_generator():
        last_payload = None

        while True:
            if await request.is_disconnected():
                break

            try:
                status_payload = await _build_conversation_attachment_status_payload(conversation_id, file_id)
            except HTTPException as exc:
                payload = {
                    "conversation_id": conversation_id,
                    "file_id": file_id,
                    "status": "not_found",
                    "error": exc.detail,
                }
                yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                break

            payload = status_payload.model_dump()
            serialized = json.dumps(payload, ensure_ascii=False)
            if serialized != last_payload:
                yield f"event: progress\ndata: {serialized}\n\n"
                last_payload = serialized

            if (
                payload["status"] in TERMINAL_ATTACHMENT_STATUSES
                or int(payload.get("progress_percentage") or 0) >= 100
            ):
                yield f"event: done\ndata: {serialized}\n\n"
                break

            await asyncio.sleep(interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
