"""文档管理路由（知识库功能）"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status, BackgroundTasks, Query, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import asyncio
import json
import os
import traceback
from database.mongodb import mongodb
from database.qdrant_client import qdrant_client
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from services.document_ingestion import get_chunk_repo, get_document_repo
from services.document_task_dispatcher import enqueue_document_processing
from utils.logger import logger
from utils.chunk_metadata import build_chunk_preview, build_chunk_preview_facets, filter_chunks_for_preview

router = APIRouter()

# 文档上传目录
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 文档仓储和入库流水线在 services.document_ingestion 中延迟初始化，
# router 只保留 HTTP 入参校验、响应组装和轻量查询。


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    assistant_id: Optional[str] = Form(None),
    knowledge_space_id: Optional[str] = Form(None),
):
    """
    上传文档（匿名模式）
    
    支持的文件类型：PDF, Word, Markdown, TXT
    会自动检查重复内容，相同内容的文档不能重复上传
    """
    # 匿名模式：不做管理员/配额限制
    import hashlib
    
    # 检查文件名
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件名不能为空"
        )
    
    logger.info(f"文档上传请求 - 文件名: {file.filename}, 文件类型: {file.content_type}")
    
    # 检查文件类型（包括可以转换的格式）
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
    
    # 保存文件并计算哈希
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    file_hash = None
    
    try:
        # 读取文件内容并检查大小
        # 对于大文件，使用流式读取以避免内存问题
        file_content = b""
        chunk_size = 1024 * 1024  # 1MB chunks
        file_size = 0
        MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB
        
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            file_size += len(chunk)
            
            # 检查文件大小（在读取过程中检查，避免读取过大文件）
            if file_size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"文件大小不能超过200MB，当前文件大小: {file_size / (1024 * 1024):.2f}MB"
                )
            
            file_content += chunk
        
        # 如果文件为空
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件不能为空"
            )
        
        # 计算文件哈希
        file_hash = hashlib.sha256(file_content).hexdigest()
        
        # 检查是否已存在相同内容的文档
        doc_repo = get_document_repo()
        duplicate_doc = doc_repo.find_duplicate_by_hash(file_hash)
        
        if duplicate_doc:
            # 删除刚保存的文件（如果已保存）
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            
            duplicate_title = duplicate_doc.get("title") or duplicate_doc.get("file_path", "").split("/")[-1] or f"文档_{duplicate_doc.get('_id', 'unknown')[:8]}"
            duplicate_id = duplicate_doc.get("_id", "未知ID")
            duplicate_status = duplicate_doc.get("status", "unknown")
            
            logger.warning(
                f"检测到重复文档 - 用户ID: anonymous, "
                f"文件名: {file.filename}, "
                f"已存在文档ID: {duplicate_id}, 标题: {duplicate_title}"
            )
            
            # 返回详细的重复信息
            detail_msg = (
                f"该文档内容已存在，不能重复上传。"
                f"已存在的文档：{duplicate_title} (ID: {duplicate_id}, 状态: {duplicate_status})"
            )
            
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=detail_msg
            )
        
        # 保存文件
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
        
        file_size = os.path.getsize(file_path)

        # 上传前必须明确目标知识空间
        if not knowledge_space_id and not assistant_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先选择要上传到的知识空间")

        # 向后兼容：如果只传 assistant_id，则复用为 knowledge_space_id
        if not knowledge_space_id and assistant_id:
            knowledge_space_id = assistant_id

        # 创建文档记录（初始状态为 processing）
        doc_id = doc_repo.create_document(
            title=file.filename,
            file_type=file_ext[1:],  # 去掉点号
            file_path=file_path,
            file_size=file_size,
            file_hash=file_hash,  # 存储文件哈希
            assistant_id=assistant_id,
            knowledge_space_id=knowledge_space_id,
        )
        
        # 记录文档创建信息
        if assistant_id:
            logger.info(f"文档已创建并关联到助手 - 文档ID: {doc_id}, 助手ID: {assistant_id}, 文件名: {file.filename}")
        else:
            logger.warning(f"文档已创建但未关联助手 - 文档ID: {doc_id}, 文件名: {file.filename}")
        
        # 设置文档状态为处理中
        doc_repo.update_document_status(doc_id, "processing")
        
        # 在后台异步处理文档，不阻塞响应（确保传递 knowledge_space_id）
        task_dispatch = enqueue_document_processing(
            background_tasks,
            file_path,
            doc_id,
            assistant_id,
            knowledge_space_id,
        )
        
        logger.info(f"文件上传成功，已启动后台处理任务 - 文档ID: {doc_id}, 助手ID: {assistant_id or '未指定'}, 文件哈希: {file_hash[:16]}...")
        
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "message": "文件上传成功，正在后台处理",
                "document_id": doc_id,
                "filename": file.filename,
                "file_size": file_size,
                "status": "processing",
                "task": task_dispatch,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        # 如果出错，尝试清理已保存的文件
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        
        # 打印完整的错误堆栈信息
        error_traceback = traceback.format_exc()
        logger.error(f"文件处理失败: {str(e)}")
        logger.error(f"错误堆栈信息:\n{error_traceback}")
        logger.error(f"文件信息 - 文件名: {file.filename if file else 'None'}, 文件路径: {file_path}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件处理失败: {str(e)}"
        )


class DocumentInfo(BaseModel):
    """文档信息模型"""
    id: str
    title: str
    file_type: str
    file_size: int
    created_at: str
    status: str
    progress_percentage: Optional[int] = None
    current_stage: Optional[str] = None
    stage_details: Optional[str] = None
    parse_quality: Optional[Dict[str, Any]] = None


class DocumentProgressResponse(BaseModel):
    """文档进度响应模型"""
    document_id: str
    progress_percentage: int
    current_stage: str
    stage_details: str
    status: str


TERMINAL_DOCUMENT_STATUSES = {"completed", "failed"}


def _build_document_progress_payload(doc_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "document_id": doc_id,
        "progress_percentage": doc.get("progress_percentage", 0),
        "current_stage": doc.get("current_stage", "未知"),
        "stage_details": doc.get("stage_details", ""),
        "status": doc.get("status", "unknown"),
    }


class DocumentListResponse(BaseModel):
    """文档列表响应模型"""
    documents: List[DocumentInfo]
    total: int


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    skip: int = 0,
    limit: int = 100,
    assistant_id: Optional[str] = None,
    knowledge_space_id: Optional[str] = None,
):
    """
    获取文档列表（匿名模式）
    """
    logger.info(f"获取文档列表请求 - skip: {skip}, limit: {limit}, assistant_id: {assistant_id}")
    
    # 所有管理员都可以查看所有文档，不再按assistant_id过滤
    # assistant_id参数仅用于筛选特定助手的文档（可选）
    
    try:
        repo = get_document_repo()
        
        # 查询所有文档（如果指定了assistant_id则筛选该助手的文档）
        docs = repo.list_documents(skip=skip, limit=limit, assistant_id=assistant_id, knowledge_space_id=knowledge_space_id)
        
        # 获取总数量（用于分页）
        total_count = repo.count_documents(assistant_id=assistant_id, knowledge_space_id=knowledge_space_id)
        
        document_list = []
        for doc in docs:
            try:
                document_info = DocumentInfo(
                    id=doc["_id"],
                    title=doc["title"],
                    file_type=doc["file_type"],
                    file_size=doc["file_size"],
                    created_at=doc["created_at"].isoformat() if isinstance(doc["created_at"], datetime) else str(doc["created_at"]),
                    status=doc.get("status", "unknown"),
                    progress_percentage=doc.get("progress_percentage"),
                    current_stage=doc.get("current_stage"),
                    stage_details=doc.get("stage_details"),
                    parse_quality=(doc.get("metadata") or {}).get("parse_quality")
                )
                document_list.append(document_info)
            except Exception as e:
                logger.warning(f"转换文档数据失败: {str(e)}")
                continue
        
        logger.info(f"文档列表查询成功 - 返回 {len(document_list)} 条记录，总计 {total_count} 条")
        return DocumentListResponse(documents=document_list, total=total_count)
    except Exception as e:
        logger.error(f"获取文档列表失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档列表失败: {str(e)}"
        )


@router.get("/{doc_id}/progress", response_model=DocumentProgressResponse)
async def get_document_progress(
    doc_id: str,
):
    """获取文档处理进度"""
    logger.info(f"获取文档进度请求 - 文档ID: {doc_id}")
    
    try:
        repo = get_document_repo()
        doc = repo.get_document(doc_id)
        
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在"
            )
        
        return DocumentProgressResponse(**_build_document_progress_payload(doc_id, doc))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档进度失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档进度失败: {str(e)}"
        )


@router.get("/{doc_id}/progress/stream")
async def stream_document_progress(
    doc_id: str,
    request: Request,
    interval: float = Query(1.5, ge=0.5, le=10.0),
):
    """Stream document processing progress as server-sent events."""

    async def event_generator():
        repo = get_document_repo()
        last_payload = None

        while True:
            if await request.is_disconnected():
                break

            doc = repo.get_document(doc_id)
            if not doc:
                payload = {"document_id": doc_id, "status": "not_found", "error": "文档不存在"}
                yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                break

            payload = _build_document_progress_payload(doc_id, doc)
            serialized = json.dumps(payload, ensure_ascii=False)
            if serialized != last_payload:
                yield f"event: progress\ndata: {serialized}\n\n"
                last_payload = serialized

            if payload["status"] in TERMINAL_DOCUMENT_STATUSES or payload["progress_percentage"] >= 100:
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


class DocumentDetailResponse(BaseModel):
    """文档详情响应模型"""
    id: str
    title: str
    file_type: str
    file_size: int
    created_at: str
    updated_at: str
    status: str
    progress_percentage: Optional[int] = None
    current_stage: Optional[str] = None
    stage_details: Optional[str] = None
    file_path: str
    # 文档元数据（包含作者等信息）
    metadata: Optional[Dict[str, Any]] = None
    # 处理流程信息
    processing_stages: List[Dict[str, Any]]
    # 文档块信息
    chunks: List[Dict[str, Any]]
    # 向量信息
    vectors: List[Dict[str, Any]]
    # 统计信息
    total_chunks: int
    total_vectors: int


class DocumentChunksResponse(BaseModel):
    """文档分块预览响应模型"""
    document_id: str
    title: str
    status: str
    chunks: List[Dict[str, Any]]
    total_chunks: int
    total_all_chunks: Optional[int] = None
    skip: int
    limit: int
    parse_quality: Optional[Dict[str, Any]] = None
    facets: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None
    target_chunk_id: Optional[str] = None
    target_chunk_index: Optional[int] = None
    target_found: Optional[bool] = None
    target_offset: Optional[int] = None


@router.post("/{doc_id}/retry")
async def retry_document_processing(
    doc_id: str,
    background_tasks: BackgroundTasks,
):
    """重新处理文档（清理旧数据后重新处理）"""
    logger.info(f"重新处理文档请求 - 文档ID: {doc_id}")
    
    try:
        doc_repo = get_document_repo()
        chunk_repo = get_chunk_repo()
        
        # 1. 获取文档信息
        doc = doc_repo.get_document(doc_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在"
            )
        
        # 2. 检查文件是否存在
        file_path = doc.get("file_path")
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"文档文件不存在: {file_path}"
            )
        
        # 3. 清理旧的chunks（MongoDB）
        try:
            chunk_repo.delete_chunks_by_document(doc_id)
            logger.info(f"已清理文档的旧chunks - 文档ID: {doc_id}")
        except Exception as e:
            logger.warning(f"清理chunks失败 - 文档ID: {doc_id}, 错误: {str(e)}")
        
        # 4. 获取助手对应的集合名称
        assistant_id = doc.get("assistant_id")
        knowledge_space_id = doc.get("knowledge_space_id") or assistant_id
        collection_name = "default_knowledge"  # 默认集合（全局）
        if assistant_id:
            try:
                from bson import ObjectId
                assistant_collection = mongodb.get_collection("course_assistants")
                
                # 确保 assistant_id 转换为 ObjectId
                try:
                    if isinstance(assistant_id, str):
                        assistant_oid = ObjectId(assistant_id)
                    else:
                        assistant_oid = assistant_id
                    
                    assistant_doc = await assistant_collection.find_one({"_id": assistant_oid})
                    if assistant_doc:
                        collection_name = assistant_doc.get("collection_name", "default_knowledge")
                        logger.info(f"获取助手集合名称成功 - 助手ID: {assistant_id}, 集合名称: {collection_name}, 文档ID: {doc_id}")
                    else:
                        logger.warning(f"未找到助手记录 - 助手ID: {assistant_id}, 文档ID: {doc_id}, 使用默认集合: {collection_name}")
                except Exception as oid_error:
                    logger.warning(f"转换 assistant_id 为 ObjectId 失败: {str(oid_error)}, 助手ID: {assistant_id}, 文档ID: {doc_id}")
            except Exception as e:
                logger.error(f"获取助手集合名称失败: {str(e)}, 助手ID: {assistant_id}, 文档ID: {doc_id}, 使用默认集合: {collection_name}", exc_info=True)
        else:
            logger.warning(f"文档未关联助手 - 文档ID: {doc_id}, 使用默认集合: {collection_name}")
        
        # 5. 清理旧的vectors（Qdrant）
        try:
            from database.qdrant_client import get_qdrant_client
            qdrant_client_instance = get_qdrant_client(collection_name)
            qdrant_client_instance.delete_by_document_id(doc_id)
            logger.info(f"已清理文档的旧vectors - 文档ID: {doc_id}, 集合: {collection_name}")
        except Exception as e:
            logger.warning(f"清理vectors失败 - 文档ID: {doc_id}, 错误: {str(e)}")
        
        # 6. 重置文档状态
        doc_repo.update_document_status(doc_id, "processing")
        doc_repo.update_document_progress(doc_id, 0, "重新处理", "正在清理旧数据并重新开始处理...")
        
        # 7. 重新启动处理任务
        task_dispatch = enqueue_document_processing(
            background_tasks,
            file_path,
            doc_id,
            assistant_id,
            knowledge_space_id,
        )
        
        logger.info(f"文档重新处理任务已启动 - 文档ID: {doc_id}")
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "文档重新处理已启动",
                "document_id": doc_id,
                "status": "processing",
                "task": task_dispatch,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新处理文档失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重新处理文档失败: {str(e)}"
        )


@router.get("/{doc_id}/chunks", response_model=DocumentChunksResponse)
async def get_document_chunks(
    doc_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    include_text: bool = Query(True),
    content_type: Optional[str] = Query(None),
    feature: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    target_chunk_id: Optional[str] = Query(None),
    target_chunk_index: Optional[int] = Query(None, ge=0),
    context_window: int = Query(4, ge=0, le=50),
):
    """获取文档分块预览，用于切块可视化和证据定位。"""
    logger.info(f"获取文档分块预览请求 - 文档ID: {doc_id}, skip: {skip}, limit: {limit}")

    try:
        doc_repo = get_document_repo()
        chunk_repo = get_chunk_repo()

        doc = doc_repo.get_document(doc_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在"
            )

        chunks = chunk_repo.get_chunks_by_document(doc_id)
        total_all = len(chunks)
        filtered_chunks = filter_chunks_for_preview(
            chunks,
            content_type=content_type,
            feature=feature,
            query=q,
        )
        total = len(filtered_chunks)

        target_position: Optional[int] = None
        target_found = False
        if target_chunk_id or target_chunk_index is not None:
            if target_chunk_id:
                for index, chunk in enumerate(filtered_chunks):
                    chunk_id = str(chunk.get("_id") or chunk.get("id") or "")
                    if chunk_id == target_chunk_id:
                        target_position = index
                        break
            if target_position is None and target_chunk_index is not None:
                for index, chunk in enumerate(filtered_chunks):
                    chunk_index = chunk.get("chunk_index")
                    if chunk_index == target_chunk_index:
                        target_position = index
                        break

            target_found = target_position is not None
            if target_found:
                max_skip = max(total - limit, 0)
                desired_skip = max(0, int(target_position or 0) - min(context_window, max(limit - 1, 0)))
                skip = min(desired_skip, max_skip)

        page = filtered_chunks[skip: skip + limit]
        previews = [build_chunk_preview(chunk, include_text=include_text) for chunk in page]
        target_offset = (target_position - skip) if target_position is not None and skip <= target_position < skip + len(page) else None
        if target_found and target_position is not None:
            target_chunk = filtered_chunks[target_position]
            target_chunk_id = str(target_chunk.get("_id") or target_chunk.get("id") or target_chunk_id or "")
            raw_target_index = target_chunk.get("chunk_index")
            target_chunk_index = raw_target_index if isinstance(raw_target_index, int) else target_chunk_index
        parse_quality = (doc.get("metadata") or {}).get("parse_quality")
        if not parse_quality and chunks:
            parse_quality = ((chunks[0].get("metadata") or {}).get("parse_summary") or None)
        facets = build_chunk_preview_facets(chunks)

        return DocumentChunksResponse(
            document_id=doc["_id"],
            title=doc.get("title", ""),
            status=doc.get("status", "unknown"),
            chunks=previews,
            total_chunks=total,
            total_all_chunks=total_all,
            skip=skip,
            limit=limit,
            parse_quality=parse_quality,
            facets=facets,
            filters={
                "content_type": content_type,
                "feature": feature,
                "q": q,
            },
            target_chunk_id=target_chunk_id,
            target_chunk_index=target_chunk_index,
            target_found=target_found if target_chunk_id or target_chunk_index is not None else None,
            target_offset=target_offset,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档分块预览失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档分块预览失败: {str(e)}"
        )


@router.get("/{doc_id}", response_model=DocumentDetailResponse)
async def get_document_detail(
    doc_id: str,
):
    """获取文档详情（包括处理流程、文本块和向量信息）"""
    logger.info(f"获取文档详情请求 - 文档ID: {doc_id}")
    
    try:
        doc_repo = get_document_repo()
        chunk_repo = get_chunk_repo()
        
        # 1. 获取文档基本信息
        doc = doc_repo.get_document(doc_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在"
            )
        
        # 2. 获取文档的所有块
        chunks = chunk_repo.get_chunks_by_document(doc_id)
        
        # 3. 获取文档的所有向量（从 Qdrant）
        vectors = []
        try:
            vectors = qdrant_client.get_vectors_by_document_id(doc_id)
        except Exception as e:
            logger.warning(f"获取文档向量失败 - 文档ID: {doc_id}, 错误: {str(e)}")
            # 继续处理，即使向量获取失败
        
        # 4. 构建处理流程信息
        processing_stages = []
        if doc.get("status") == "completed":
            processing_stages = [
                {"stage": "文档上传", "progress": 5, "status": "completed"},
                {"stage": "解析文档", "progress": 25, "status": "completed"},
                {"stage": "文本分块", "progress": 35, "status": "completed"},
                {"stage": "向量化", "progress": 75, "status": "completed"},
                {"stage": "存储向量", "progress": 95, "status": "completed"},
                {"stage": "完成", "progress": 100, "status": "completed"}
            ]
        elif doc.get("status") == "processing":
            current_progress = doc.get("progress_percentage", 0)
            current_stage = doc.get("current_stage", "处理中")
            
            # 根据当前进度确定已完成和进行中的阶段
            stages = [
                {"stage": "文档上传", "progress": 5},
                {"stage": "解析文档", "progress": 25},
                {"stage": "文本分块", "progress": 35},
                {"stage": "向量化", "progress": 75},
                {"stage": "存储向量", "progress": 95},
                {"stage": "完成", "progress": 100}
            ]
            
            for stage in stages:
                if current_progress >= stage["progress"]:
                    stage["status"] = "completed"
                elif current_stage == stage["stage"] or (current_progress < stage["progress"] and current_progress >= stage["progress"] - 20):
                    stage["status"] = "processing"
                else:
                    stage["status"] = "pending"
                processing_stages.append(stage)
        elif doc.get("status") == "failed":
            processing_stages = [
                {"stage": "文档上传", "progress": 5, "status": "completed"},
                {"stage": "处理失败", "progress": doc.get("progress_percentage", 0), "status": "failed", "error": doc.get("stage_details", "")}
            ]
        else:
            processing_stages = [
                {"stage": "未知状态", "progress": 0, "status": "unknown"}
            ]
        
        return DocumentDetailResponse(
            id=doc["_id"],
            title=doc["title"],
            file_type=doc["file_type"],
            file_size=doc["file_size"],
            created_at=doc["created_at"].isoformat() if isinstance(doc["created_at"], datetime) else str(doc["created_at"]),
            updated_at=doc["updated_at"].isoformat() if isinstance(doc["updated_at"], datetime) else str(doc["updated_at"]),
            status=doc.get("status", "unknown"),
            progress_percentage=doc.get("progress_percentage"),
            current_stage=doc.get("current_stage"),
            stage_details=doc.get("stage_details"),
            file_path=doc.get("file_path", ""),
            metadata=doc.get("metadata", {}),  # 包含作者等元数据
            processing_stages=processing_stages,
            chunks=chunks,
            vectors=vectors,
            total_chunks=len(chunks),
            total_vectors=len(vectors)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档详情失败: {str(e)}"
        )


class DocumentUpdateRequest(BaseModel):
    """文档更新请求模型"""
    title: str


@router.put("/{doc_id}")
async def update_document(
    doc_id: str,
    request: DocumentUpdateRequest,
):
    """更新文档（主要是重命名，匿名模式）"""
    logger.info(f"更新文档请求 - 文档ID: {doc_id}, 新标题: {request.title}")
    
    try:
        doc_repo = get_document_repo()
        
        # 检查文档是否存在
        doc = doc_repo.get_document(doc_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在"
            )
        
        # 所有管理员都可以修改文档（知识库共享）
        # 不再检查assistant_id权限
        
        # 验证标题
        if not request.title or not request.title.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文档标题不能为空"
            )
        
        # 更新文档标题
        doc_repo.update_document_title(doc_id, request.title.strip())
        
        logger.info(f"文档更新成功 - 文档ID: {doc_id}, 新标题: {request.title}")
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "文档更新成功",
                "document_id": doc_id,
                "title": request.title.strip()
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新文档失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新文档失败: {str(e)}"
        )


@router.get("/{doc_id}/preview")
async def preview_document(
    doc_id: str,
):
    """预览文档文件（所有认证用户都可以访问）"""
    logger.info(f"预览文档请求 - 文档ID: {doc_id}")
    
    try:
        doc_repo = get_document_repo()
        doc = doc_repo.get_document(doc_id)
        
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在"
            )
        
        file_path = doc.get("file_path")
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档文件不存在"
            )
        
        # 获取文件名
        filename = os.path.basename(file_path)
        if not filename:
            filename = doc.get("title", "document")
        
        # 根据文件类型设置媒体类型
        file_type = doc.get("file_type", "").lower()
        media_type_map = {
            "pdf": "application/pdf",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "txt": "text/plain",
            "md": "text/markdown",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        media_type = media_type_map.get(file_type, "application/octet-stream")
        
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=media_type,
            content_disposition_type="inline",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预览文档失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"预览文档失败: {str(e)}"
        )


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
):
    """删除文档（包括清理chunks、vectors和文件，匿名模式）"""
    logger.info(f"删除文档请求 - 文档ID: {doc_id}")
    
    try:
        doc_repo = get_document_repo()
        chunk_repo = get_chunk_repo()
        
        # 1. 获取文档信息（如果不存在，也继续执行清理操作）
        doc = doc_repo.get_document(doc_id)
        
        # 所有管理员都可以删除文档（知识库共享）
        # 不再检查assistant_id权限
        
        file_path = doc.get("file_path") if doc else None
        
        # 2. 清理chunks（MongoDB）- 即使文档不存在也尝试清理
        try:
            chunk_repo.delete_chunks_by_document(doc_id)
            logger.info(f"已清理文档的chunks - 文档ID: {doc_id}")
        except Exception as e:
            logger.warning(f"清理chunks失败 - 文档ID: {doc_id}, 错误: {str(e)}")
        
        # 3. 清理vectors（Qdrant）- 即使文档不存在也尝试清理
        try:
            qdrant_client.delete_by_document_id(doc_id)
            logger.info(f"已清理文档的vectors - 文档ID: {doc_id}")
        except Exception as e:
            logger.warning(f"清理vectors失败 - 文档ID: {doc_id}, 错误: {str(e)}")
        
        # 4. 删除文件（如果存在）
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"已删除文档文件 - 文件路径: {file_path}")
            except Exception as e:
                logger.warning(f"删除文件失败 - 文件路径: {file_path}, 错误: {str(e)}")
        
        # 5. 删除文档记录（MongoDB）- 如果文档存在才删除
        deleted = False
        if doc:
            try:
                deleted = doc_repo.delete_document(doc_id)
                if deleted:
                    logger.info(f"已删除文档记录 - 文档ID: {doc_id}")
                else:
                    logger.warning(f"删除文档记录失败 - 文档ID: {doc_id}, 未找到匹配的文档（可能已被删除）")
            except Exception as e:
                logger.error(f"删除文档记录失败 - 文档ID: {doc_id}, 错误: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"删除文档记录失败: {str(e)}"
                )
        else:
            logger.info(f"文档记录不存在（可能已被删除），跳过删除记录步骤 - 文档ID: {doc_id}")
        
        # 返回成功（即使文档记录不存在，也已经清理了chunks、vectors和文件）
        logger.info(f"文档删除操作完成 - 文档ID: {doc_id}")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "文档删除成功",
                "document_id": doc_id
            }
        )
    except Exception as e:
        logger.error(f"删除文档失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除文档失败: {str(e)}"
        )

