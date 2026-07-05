"""文档管理路由（知识库功能）"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status, BackgroundTasks, Query
from fastapi.responses import JSONResponse, FileResponse
import os
import shutil
import traceback
from database.mongodb import DocumentRepository, ChunkRepository, ResourceRepository, mongodb_client, mongodb
from database.qdrant_client import qdrant_client
from parsers.parser_factory import ParserFactory  # 保持向后兼容
from parsers.router import ParsingRouter  # 解析路由模块
from parsers.utils import ResultSynthesizer  # 解析工具模块
from chunking.simple_chunker import SimpleChunker  # 保持向后兼容
from chunking.router import ContentAnalyzer  # 分块路由模块
from embedding.embedding_service import embedding_service
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from utils.logger import logger
from utils.chunk_metadata import build_chunk_preview, build_parse_quality_summary, build_retrieval_payload_metadata, enrich_chunks_for_visualization, filter_chunks_for_preview

router = APIRouter()

# 文档上传目录
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 延迟初始化知识库组件，避免启动时数据库连接超时导致服务无法响应
# MongoDB 连接将在首次使用时建立（lazy initialization）
document_repo = None
chunk_repo = None

def get_document_repo():
    """获取文档仓库（延迟初始化）"""
    global document_repo
    if document_repo is None:
        mongodb_client.connect()
        document_repo = DocumentRepository(mongodb_client)
    return document_repo

def get_chunk_repo():
    """获取分块仓库（延迟初始化）"""
    global chunk_repo
    if chunk_repo is None:
        mongodb_client.connect()
        chunk_repo = ChunkRepository(mongodb_client)
    return chunk_repo


def _parse_pdf_with_progress(file_path: str, doc_repo, doc_id: str) -> dict:
    """带进度显示的PDF解析"""
    import PyPDF2
    import time
    
    text_content = []
    metadata = {}
    
    with open(file_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        total_pages = len(pdf_reader.pages)
        
        logger.info(f"PDF文件总页数: {total_pages}")
        
        # 提取元数据
        if pdf_reader.metadata:
            metadata = {
                "title": pdf_reader.metadata.get("/Title", ""),
                "author": pdf_reader.metadata.get("/Author", ""),
                "subject": pdf_reader.metadata.get("/Subject", ""),
                "pages": total_pages
            }
        
        # 逐页解析并显示进度
        logger.info("正在逐页解析PDF...")
        start_time = time.time()
        
        for page_num, page in enumerate(pdf_reader.pages):
            try:
                page_start = time.time()
                text = page.extract_text()
                
                if text.strip():
                    text_content.append({
                        "page": page_num + 1,
                        "text": text
                    })
                
                # 每10页或每5秒更新一次进度
                elapsed = time.time() - start_time
                if (page_num + 1) % 10 == 0 or (page_num + 1) == total_pages or elapsed >= 5.0:
                    progress = 5 + int(((page_num + 1) / total_pages) * 20)  # 5-25%
                    doc_repo.update_document_progress(
                        doc_id,
                        progress,
                        "解析文档",
                        f"已解析: {page_num + 1}/{total_pages} 页"
                    )
                    start_time = time.time()  # 重置计时器
            
            except Exception as e:
                logger.warning(f"第 {page_num + 1} 页解析失败: {e}")
                continue
        
        full_text = "\n\n".join([page["text"] for page in text_content])
        
        return {
            "text": full_text,
            "metadata": {
                **metadata,
                "page_count": total_pages,
                "pages": text_content
            }
        }


def _parse_with_timeout(parser, file_path: str, doc_repo, doc_id: str) -> dict:
    """带超时监控的解析"""
    import threading
    import time
    
    # 创建一个标志来跟踪解析是否完成
    parse_complete = threading.Event()
    parse_result = [None]
    parse_exception = [None]
    
    def parse_with_monitor():
        try:
            logger.info(f"开始解析文件 - 文件路径: {file_path}, 解析器类型: {type(parser).__name__}")
            result = parser.parse(file_path)
            
            # 验证解析结果
            if not result:
                raise Exception("解析器返回空结果")
            if "text" not in result:
                raise Exception("解析结果中缺少'text'字段")
            
            text_len = len(result.get("text", ""))
            logger.info(f"解析器返回结果 - 文本长度: {text_len}, 元数据键: {list(result.get('metadata', {}).keys())}")
            
            parse_result[0] = result
        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.error(f"解析过程中出错 - 文件路径: {file_path}, 错误: {str(e)}")
            logger.error(f"解析错误堆栈:\n{error_traceback}")
            parse_exception[0] = e
        finally:
            parse_complete.set()
    
    # 启动解析线程
    parse_thread = threading.Thread(target=parse_with_monitor, daemon=True)
    parse_thread.start()
    
    # 显示进度（每1秒更新一次）
    start_time = time.time()
    timeout_seconds = 900  # 15分钟超时（支持大文件处理）
    
    while not parse_complete.is_set():
        if parse_thread.is_alive():
            elapsed = time.time() - start_time
            
            # 检查超时
            if elapsed > timeout_seconds:
                logger.error(f"解析超时（超过 {timeout_seconds} 秒）")
                raise TimeoutError(f"文档解析超时（超过 {timeout_seconds} 秒）")
            
            # 每5秒更新一次进度
            if int(elapsed) % 5 == 0:
                progress = 5 + int((elapsed / timeout_seconds) * 20)  # 5-25%
                doc_repo.update_document_progress(
                    doc_id,
                    min(progress, 24),
                    "解析文档",
                    f"解析中... 已用时: {elapsed:.1f}秒"
                )
            
            parse_complete.wait(timeout=0.5)
        else:
            break
    
    # 等待线程完成
    parse_thread.join(timeout=2)
    
    # 检查结果
    if parse_exception[0]:
        raise parse_exception[0]
    if parse_result[0] is None:
        raise Exception("解析超时或失败")
    
    return parse_result[0]


def _chunk_with_timeout(text: str, doc_repo, doc_id: str, metadata: Optional[Dict[str, Any]] = None) -> list:
    """带超时监控的分块（使用分块路由模块）"""
    import threading
    import time
    
    # 使用内容分析路由器选择合适的分块器
    content_analyzer = ContentAnalyzer()
    chunker_type, chunker = content_analyzer.route(text, metadata)
    logger.info(f"选择分块器类型: {chunker_type}, 文档ID: {doc_id}")
    
    # 使用线程监控分块过程
    chunk_complete = threading.Event()
    chunk_result = [None]
    chunk_exception = [None]
    
    def chunk_with_monitor():
        try:
            logger.info(f"开始分块 - 文档ID: {doc_id}, 文本长度: {len(text)}, 分块器类型: {chunker_type}")
            chunk_metadata = {"document_id": doc_id, "chunker_type": chunker_type}
            if metadata:
                chunk_metadata.update(metadata)
            result = chunker.chunk(text, metadata=chunk_metadata)
            
            # 验证分块结果
            if result is None:
                raise Exception("分块器返回None")
            
            logger.info(f"分块器返回结果 - 块数量: {len(result)}, 文档ID: {doc_id}, 分块器类型: {chunker_type}")
            if result:
                first_chunk_text = result[0].get("text", "")[:50] if result[0].get("text") else "(空)"
                logger.info(f"第一个块预览（前50字符）: {first_chunk_text}")
            
            chunk_result[0] = result
        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.error(f"分块过程中出错 - 文档ID: {doc_id}, 错误: {str(e)}")
            logger.error(f"分块错误堆栈:\n{error_traceback}")
            chunk_exception[0] = e
        finally:
            chunk_complete.set()
    
    chunk_thread = threading.Thread(target=chunk_with_monitor, daemon=True)
    chunk_thread.start()
    
    # 显示进度（每2秒更新一次）
    timeout_seconds = 1800  # 30分钟超时（支持大文件处理）
    start_time = time.time()
    last_update = start_time
    
    while not chunk_complete.is_set():
        if chunk_thread.is_alive():
            elapsed = time.time() - start_time
            
            # 检查超时
            if elapsed > timeout_seconds:
                logger.error(f"分块超时（超过 {timeout_seconds} 秒）")
                raise TimeoutError(f"分块超时（超过 {timeout_seconds} 秒）")
            
            # 每2秒更新一次进度
            if time.time() - last_update >= 2.0:
                progress = 25 + int((elapsed / timeout_seconds) * 10)  # 25-35%
                doc_repo.update_document_progress(
                    doc_id,
                    min(progress, 34),
                    "文本分块",
                    f"分块中... ({chunker_type}) 已用时: {elapsed:.1f}秒"
                )
                last_update = time.time()
            
            chunk_complete.wait(timeout=0.5)
        else:
            break
    
    # 等待完成
    chunk_thread.join(timeout=2)
    
    if chunk_exception[0]:
        raise chunk_exception[0]
    if chunk_result[0] is None:
        raise Exception("分块失败或超时")
    
    return chunk_result[0]


def process_document_background(
    file_path: str,
    doc_id: str,
    assistant_id: Optional[str] = None,
    knowledge_space_id: Optional[str] = None,
):
    """后台处理文档：解析、分块、向量化（同步函数，在后台线程中执行）"""
    import traceback
    import math
    import os
    
    try:
        logger.info(f"开始后台处理文档 - 文档ID: {doc_id}, 文件路径: {file_path}")
        
        # 确保 MongoDB 连接已建立
        mongodb_client.connect()
        doc_repo = get_document_repo()
        
        # 阶段1 (5%): 开始解析文档
        doc_repo.update_document_progress(doc_id, 5, "解析文档", "正在提取纯文本内容...")
        
        file_ext = os.path.splitext(file_path)[1].lower()
        original_file_path = file_path
        converted_file_path = None
        
        # 如果是.doc格式，先转换为.docx
        if file_ext == ".doc":
            try:
                from utils.document_converter import DocumentConverter
                doc_repo.update_document_progress(doc_id, 6, "转换文档", "正在将.doc格式转换为.docx...")
                converted_file_path = DocumentConverter.convert_doc_to_docx(file_path)
                
                if converted_file_path and os.path.exists(converted_file_path):
                    logger.info(f"文档转换成功: {file_path} -> {converted_file_path}")
                    file_path = converted_file_path  # 使用转换后的.docx文件
                    file_ext = ".docx"  # 更新文件扩展名
                else:
                    raise Exception(f"无法将.doc文件转换为.docx")
            except Exception as e:
                logger.error(f"文档转换失败: {str(e)}", exc_info=True)
                raise Exception(f"无法处理.doc格式文件: {str(e)}。请将文件转换为.docx格式后上传。")
        
        # 1. 解析文档（使用增强解析模块）
        try:
            # 使用解析路由器选择合适的解析器
            parsing_router = ParsingRouter()
            parser_type, parser = parsing_router.route(file_path)
            logger.info(f"选择解析器类型: {parser_type}, 文件: {file_path}")
            
            # 对于PDF文件，如果是原有解析器，使用带进度显示的解析
            if file_ext == ".pdf" and parser_type == ParsingRouter.PARSER_TYPE_LEGACY:
                parser_class_name = type(parser).__name__
                if parser_class_name == "PDFParser":
                    try:
                        parsed_data = _parse_pdf_with_progress(file_path, doc_repo, doc_id)
                    except Exception as e:
                        logger.warning(f"带进度的PDF解析失败，使用默认解析器: {e}")
                        parsed_data = _parse_with_timeout(parser, file_path, doc_repo, doc_id)
                else:
                    parsed_data = _parse_with_timeout(parser, file_path, doc_repo, doc_id)
            else:
                # 对于其他解析器类型，使用标准解析（带超时监控）
                parsed_data = _parse_with_timeout(parser, file_path, doc_repo, doc_id)
            
            # 使用结果合成器统一输出格式
            synthesizer = ResultSynthesizer(
                merge_tables_into_text=True,
                merge_code_blocks_into_text=True,
                use_raw_markdown_if_present=True,
            )
            parsed_data = synthesizer.synthesize(parsed_data, parser_type, file_path)
            
        except Exception as e:
            # 如果增强解析模块失败，回退到原有解析器
            logger.warning(f"增强解析模块失败，回退到原有解析器: {e}")
            parser = ParserFactory.get_parser(file_path)
            if not parser:
                raise ValueError(f"不支持的文件类型: {file_path}")
            
            parser_class_name = type(parser).__name__
            
            # 对于PDF文件，使用带进度显示的解析
            if file_ext == ".pdf" and parser_class_name == "PDFParser":
                try:
                    parsed_data = _parse_pdf_with_progress(file_path, doc_repo, doc_id)
                except Exception as e:
                    logger.warning(f"带进度的PDF解析失败，使用默认解析器: {e}")
                    parsed_data = _parse_with_timeout(parser, file_path, doc_repo, doc_id)
            else:
                # 对于其他文件类型，使用标准解析（带超时监控）
                parsed_data = _parse_with_timeout(parser, file_path, doc_repo, doc_id)
        
        text = parsed_data.get("text", "")
        metadata = parsed_data.get("metadata", {})
        
        # 检查解析结果
        if not text or not text.strip():
            # 文本提取失败，直接标记为失败
            error_msg = f"文档解析失败：未提取到任何文本内容。文件类型: {file_ext}, 文件路径: {file_path}"
            logger.error(error_msg)
            logger.error(f"解析器类型: {parser_class_name}, 元数据: {metadata}")
            doc_repo.update_document_status(doc_id, "failed")
            doc_repo.update_document_progress(doc_id, 0, "失败", "解析失败：未提取到文本内容（可能是扫描版PDF或文件损坏）")
            return
        
        # 详细日志：记录解析结果
        text_preview = text[:200] if text else "(空)"
        extraction_method = metadata.get("extraction_method", "text_extraction")
        logger.info(f"文档解析完成 - 文档ID: {doc_id}, 文本长度: {len(text)}, 文件类型: {file_ext}, 提取方法: {extraction_method}")
        logger.info(f"解析结果预览（前200字符）: {text_preview}")
        
        # 阶段2 (25%): 解析完成，开始分块
        doc_repo.update_document_progress(doc_id, 25, "文本分块", f"文本长度: {len(text)} 字符")
        
        # 2. 文本分块（使用分块路由模块，带超时监控）
        # 添加文件类型信息到元数据，用于内容分析
        chunk_metadata = metadata.copy() if metadata else {}
        chunk_metadata["file_type"] = file_ext
        chunks = _chunk_with_timeout(text, doc_repo, doc_id, chunk_metadata)

        # 为后续重排/动态调参提供基本 token 统计（近似，不依赖外部 tokenizer）
        try:
            from utils.token_utils import estimate_tokens

            for c in chunks:
                if not isinstance(c, dict):
                    continue
                c_meta = c.get("metadata") or {}
                if "token_count" not in c_meta:
                    c_meta = c_meta.copy()
                    c_meta["token_count"] = estimate_tokens(c.get("text", ""))
                    c["metadata"] = c_meta
        except Exception:
            # 统计失败不影响主流程
            pass

        chunks = enrich_chunks_for_visualization(
            chunks,
            text,
            metadata,
            document_id=doc_id,
        )
        parse_quality = build_parse_quality_summary(metadata, text, chunks)
        for chunk in chunks:
            chunk_meta = chunk.get("metadata") or {}
            chunk_meta = chunk_meta.copy()
            chunk_meta["parse_summary"] = parse_quality
            chunk["metadata"] = chunk_meta
        try:
            doc_repo.update_document_metadata(doc_id, {"parse_quality": parse_quality})
        except Exception as e:
            logger.warning(f"更新文档解析质量摘要失败 - 文档ID: {doc_id}, 错误: {e}")
        
        logger.info(f"文档分块完成 - 文档ID: {doc_id}, 块数量: {len(chunks)}")
        
        # 记录分块结果预览
        if chunks:
            first_chunk_preview = chunks[0].get("text", "")[:100] if chunks[0].get("text") else "(空)"
            logger.info(f"第一个文本块预览（前100字符）: {first_chunk_preview}")
        else:
            logger.warning(f"分块结果为空 - 文档ID: {doc_id}, 原始文本长度: {len(text)}")
        
        # 阶段2.5: 知识抽取与图谱构建 (High-level RAG)
        try:
            from services.runtime_config import get_runtime_config_sync
            from services.knowledge_extraction_service import knowledge_extraction_service
            import asyncio
            
            runtime_cfg = get_runtime_config_sync()
            modules = runtime_cfg.get("modules") or {}
            params = runtime_cfg.get("params") or {}
            if not bool(modules.get("kg_extract_enabled", True)):
                logger.info(f"已按运行时配置跳过知识图谱构建 - 文档ID: {doc_id}")
            else:
                logger.info(f"开始知识图谱构建 - 文档ID: {doc_id}, 块数量: {len(chunks)}")
                doc_repo.update_document_progress(doc_id, 30, "知识图谱构建", "正在抽取实体关系...")

                # 定义异步任务
                async def build_kg_for_chunks():
                    tasks = []
                    # 限制并发数（默认 3）
                    kg_concurrency = int(params.get("kg_concurrency") or 3)
                    sem = asyncio.Semaphore(max(1, kg_concurrency))
                    chunk_timeout_s = int(params.get("kg_chunk_timeout_s") or 150)
                    kg_max_chunks = int(params.get("kg_max_chunks") or 0)

                    async def processed_chunk(chunk, idx):
                        async with sem:
                            meta = chunk.get("metadata", {}).copy()
                            meta["document_id"] = doc_id
                            meta["chunk_index"] = idx
                            # 仅对文本类型的块进行抽取
                            if meta.get("content_type", "text") == "text":
                                try:
                                    # 单 chunk 超时保护，避免某个 chunk 把整体卡死在 30%
                                    await asyncio.wait_for(
                                        knowledge_extraction_service.build_graph(chunk["text"], meta),
                                        timeout=max(10, chunk_timeout_s),
                                    )
                                except asyncio.TimeoutError:
                                    logger.warning(f"知识图谱构建超时，已跳过 chunk - 文档ID: {doc_id}, chunk_index: {idx}")
                                except Exception as e:
                                    logger.warning(
                                        f"知识图谱构建失败，已跳过 chunk - 文档ID: {doc_id}, chunk_index: {idx}, 错误: {e}"
                                    )

                    # 可选：限制最大处理 chunks（用于低配/长文档降级）
                    target_chunks = chunks
                    if kg_max_chunks and kg_max_chunks > 0 and len(chunks) > kg_max_chunks:
                        target_chunks = chunks[:kg_max_chunks]
                        logger.info(f"知识图谱构建将仅处理前 {kg_max_chunks}/{len(chunks)} 个块 - 文档ID: {doc_id}")

                    for i, chunk in enumerate(target_chunks):
                        tasks.append(processed_chunk(chunk, i))

                    # 分批处理，避免任务队列过长
                    batch_size = 10
                    for i in range(0, len(tasks), batch_size):
                        batch_tasks = tasks[i : i + batch_size]
                        # 不因单任务异常导致整批失败（processed_chunk 内也会兜底）
                        await asyncio.gather(*batch_tasks, return_exceptions=True)
                        # 更新进度
                        progress = 30 + int(((i + len(batch_tasks)) / len(tasks)) * 5)  # 30-35%
                        doc_repo.update_document_progress(
                            doc_id,
                            progress,
                            "知识图谱构建",
                            f"已处理 {min(i + batch_size, len(tasks))}/{len(tasks)} 块",
                        )

                # 运行异步任务
                # 注意：如果当前已经在 loop 中，asyncio.run 会失败。
                # 但 process_document_background 是在线程池中运行的，通常没有 loop。
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 理论上不应该发生，因为是在线程池中
                        logger.warning("在运行中的循环中检测到知识图谱构建，尝试使用 run_coroutine_threadsafe (可能不支持)")
                    else:
                        loop.run_until_complete(build_kg_for_chunks())
                except RuntimeError:
                    # 没有 loop
                    asyncio.run(build_kg_for_chunks())

                logger.info(f"知识图谱构建完成 - 文档ID: {doc_id}")
            
        except Exception as e:
            logger.error(f"知识图谱构建失败 (非致命错误): {e}", exc_info=True)
            # 不中断主流程

        # 阶段3 (35%): 分块完成，开始向量化
        doc_repo.update_document_progress(doc_id, 35, "向量化", f"共 {len(chunks)} 个文本块")
        
        # 3. 向量化（分批处理，避免内存问题）
        chunk_texts = [chunk["text"] for chunk in chunks]
        
        if not chunk_texts:
            logger.warning(f"文档分块为空 - 文档ID: {doc_id}")
            doc_repo.update_document_status(doc_id, "completed")
            doc_repo.update_document_progress(doc_id, 100, "完成", "文档为空，无需处理")
            return
        
        # 分批向量化（batch_size 可由运行时配置覆盖）
        try:
            from services.runtime_config import get_runtime_config_sync
            runtime_cfg = get_runtime_config_sync()
            params = runtime_cfg.get("params") or {}
            batch_size = int(params.get("embedding_batch_size") or 50)
        except Exception:
            batch_size = 50
        batch_size = max(1, batch_size)
        vectors = []
        total_batches = math.ceil(len(chunk_texts) / batch_size)
        
        for i in range(0, len(chunk_texts), batch_size):
            batch = chunk_texts[i:i + batch_size]
            try:
                batch_vectors = embedding_service.encode(batch)
                vectors.extend(batch_vectors)
                
                # 阶段4 (35-75%): 向量化过程中更新进度
                # 计算: 35 + (已处理批次 / 总批次) * 40
                current_batch = (i // batch_size) + 1
                progress = 35 + int((current_batch / total_batches) * 40)
                doc_repo.update_document_progress(
                    doc_id,
                    progress,
                    "向量化",
                    f"批次 {current_batch}/{total_batches} ({min(i + batch_size, len(chunk_texts))}/{len(chunk_texts)} 个块)"
                )
                
                logger.info(f"向量化进度 - 文档ID: {doc_id}, {min(i + batch_size, len(chunk_texts))}/{len(chunk_texts)}")
            except Exception as e:
                logger.error(f"向量化失败 - 文档ID: {doc_id}, 批次 {i//batch_size + 1}, 错误: {str(e)}")
                raise
        
        logger.info(f"文档向量化完成 - 文档ID: {doc_id}, 向量数量: {len(vectors)}")
        
        # 阶段5 (75%): 向量化完成，开始存储
        doc_repo.update_document_progress(doc_id, 75, "存储向量", "正在存储到数据库...")
        
        # 4. 获取知识空间对应的集合名称（同步方式）
        # 首先从文档记录中获取 knowledge_space_id（如果传入为 None）
        if not knowledge_space_id:
            try:
                from bson import ObjectId
                doc_record = doc_repo.get_document(doc_id)
                if doc_record and doc_record.get("knowledge_space_id"):
                    knowledge_space_id = doc_record.get("knowledge_space_id")
                    logger.info(f"从文档记录中获取 knowledge_space_id: {knowledge_space_id} - 文档ID: {doc_id}")
            except Exception as e:
                logger.warning(f"从文档记录获取 knowledge_space_id 失败: {str(e)}")
        
        # 获取知识空间对应的集合名称
        # 若未指定 knowledge_space_id，则写入全局默认集合
        collection_name = "default_knowledge"
        if knowledge_space_id:
            try:
                # 使用同步MongoDB客户端获取助手信息
                from pymongo import MongoClient
                from bson import ObjectId
                import os
                mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/advanced_rag")
                sync_client = MongoClient(mongodb_uri)
                db_name = os.getenv("MONGODB_DB_NAME", "advanced_rag")
                db = sync_client[db_name]
                
                # 确保 knowledge_space_id 转换为 ObjectId
                try:
                    if isinstance(knowledge_space_id, str):
                        space_oid = ObjectId(knowledge_space_id)
                    else:
                        space_oid = knowledge_space_id
                    
                    space_doc = db["knowledge_spaces"].find_one({"_id": space_oid})
                    if space_doc:
                        collection_name = space_doc.get("collection_name", "default_knowledge")
                        logger.info(f"获取知识空间集合名称成功 - 知识空间ID: {knowledge_space_id}, 集合名称: {collection_name}, 文档ID: {doc_id}")
                    else:
                        logger.warning(f"未找到知识空间记录 - 知识空间ID: {knowledge_space_id}, 文档ID: {doc_id}, 使用默认集合: {collection_name}")
                except Exception as oid_error:
                    logger.warning(f"转换 knowledge_space_id 为 ObjectId 失败: {str(oid_error)}, 知识空间ID: {knowledge_space_id}, 文档ID: {doc_id}")
                
                sync_client.close()
            except Exception as e:
                logger.error(f"获取知识空间集合名称失败: {str(e)}, 知识空间ID: {knowledge_space_id}, 文档ID: {doc_id}, 使用默认集合: {collection_name}", exc_info=True)
        else:
            logger.warning(f"文档未关联知识空间 - 文档ID: {doc_id}, 使用默认集合: {collection_name}")
        
        # 5. 检查 Qdrant 服务是否可用
        from database.qdrant_client import get_qdrant_client
        logger.info(f"准备存储向量到知识库 - 文档ID: {doc_id}, 知识空间ID: {knowledge_space_id or '未指定'}, 集合名称: {collection_name}")
        qdrant_client_instance = get_qdrant_client(collection_name)
        qdrant_available = qdrant_client_instance.check_health()
        if not qdrant_available:
            logger.warning(f"Qdrant 服务不可用，将跳过向量存储 - 文档ID: {doc_id}, 集合: {collection_name}")
            doc_repo.update_document_progress(
                doc_id, 
                85, 
                "存储向量", 
                "Qdrant 服务不可用，仅存储到 MongoDB"
            )
        else:
            # 确保 Qdrant 集合已创建（使用实际的向量维度）
            vector_dimension = embedding_service.dimension
            try:
                qdrant_client_instance.create_collection(vector_size=vector_dimension)
            except Exception as e:
                # 如果集合已存在，忽略错误
                if "already exists" not in str(e).lower():
                    logger.warning(f"无法创建 Qdrant 集合: {e}")
                    qdrant_available = False
        
        # 5. 存储到MongoDB和Qdrant（批量处理）
        chunk_ids = []
        total_chunks = len(chunks)
        
        # 先批量存储到MongoDB
        for idx, chunk in enumerate(chunks):
            try:
                chunk_id = get_chunk_repo().create_chunk(
                    document_id=doc_id,
                    chunk_index=idx,
                    text=chunk["text"],
                    metadata=chunk.get("metadata", {})
                )
                chunk_ids.append(chunk_id)
            except Exception as e:
                logger.error(f"存储块到 MongoDB 失败 (chunk {idx}): {e}")
                # 生成一个临时ID，确保后续处理不会出错
                chunk_ids.append(f"temp_{doc_id}_{idx}")
        
        # 批量存储向量到Qdrant（如果服务可用）
        qdrant_success_count = 0
        qdrant_failed_count = 0
        
        if qdrant_available:
            qdrant_batch_size = 50
            
            for batch_start in range(0, len(vectors), qdrant_batch_size):
                batch_end = min(batch_start + qdrant_batch_size, len(vectors))
                batch_vectors = vectors[batch_start:batch_end]
                batch_chunk_ids = chunk_ids[batch_start:batch_end]
                batch_chunks = chunks[batch_start:batch_end]
                
                # 构建批量payload
                batch_payloads = []
                batch_ids = []
                for i, (chunk_id, chunk) in enumerate(zip(batch_chunk_ids, batch_chunks)):
                    if chunk_id.startswith("temp_"):
                        # 跳过临时ID（MongoDB存储失败的块）
                        continue
                    meta = (chunk.get("metadata") or {}).copy()
                    # 仅保留对检索/拼接有价值且体积可控的字段
                    # section_path 可能较长，这里限制单个元素长度，避免 payload 过大
                    batch_payloads.append({
                        "chunk_id": chunk_id,
                        "document_id": doc_id,
                        "text": chunk["text"],
                        "chunk_index": batch_start + i,
                        # 用于邻居扩展与上下文去重的关键元数据
                        "metadata": build_retrieval_payload_metadata(meta)
                    })
                    batch_ids.append(chunk_id)
                
                # 只处理有效的向量
                if batch_payloads:
                    try:
                        # 获取对应的向量（只处理MongoDB存储成功的块）
                        valid_vectors = []
                        valid_payloads = []
                        valid_ids = []
                        payload_idx = 0
                        for i, chunk_id in enumerate(batch_chunk_ids):
                            if not chunk_id.startswith("temp_"):
                                valid_vectors.append(batch_vectors[i])
                                valid_payloads.append(batch_payloads[payload_idx])
                                valid_ids.append(chunk_id)
                                payload_idx += 1
                        
                        if valid_vectors:
                            qdrant_client_instance.insert_vectors(
                                vectors=valid_vectors,
                                payloads=valid_payloads,
                                ids=valid_ids,
                                max_retries=3,
                                retry_delay=1.0
                            )
                            qdrant_success_count += len(valid_vectors)
                            logger.info(f"批量存储向量到 Qdrant 成功 - 文档ID: {doc_id}, 集合: {collection_name}, 批次 {batch_start//qdrant_batch_size + 1}: {len(valid_vectors)} 个向量")
                    except Exception as e:
                        qdrant_failed_count += len(batch_payloads)
                        logger.warning(f"批量存储向量到 Qdrant 失败 - 批次 {batch_start//qdrant_batch_size + 1}: {e}")
                        # 如果连续失败，检查服务是否仍然可用
                        if qdrant_failed_count > 10:
                            if not qdrant_client.check_health():
                                logger.error(f"Qdrant 服务不可用，停止尝试存储向量 - 文档ID: {doc_id}")
                                qdrant_available = False
                                break
                
                # 阶段5 (75-95%): 存储过程中更新进度
                progress = 75 + int((batch_end / total_chunks) * 20)
                status_msg = f"已存储 {batch_end}/{total_chunks} 个块"
                if qdrant_available:
                    status_msg += f" (Qdrant: {qdrant_success_count} 成功, {qdrant_failed_count} 失败)"
                else:
                    status_msg += " (Qdrant 服务不可用)"
                doc_repo.update_document_progress(
                    doc_id,
                    progress,
                    "存储向量",
                    status_msg
                )
        else:
            # Qdrant 不可用，只更新进度
            doc_repo.update_document_progress(
                doc_id,
                90,
                "存储向量",
                f"已存储 {len(chunk_ids)}/{total_chunks} 个块到 MongoDB (Qdrant 服务不可用)"
            )
        
        # 记录最终统计
        if not qdrant_available:
            logger.warning(
                f"文档存储完成（Qdrant 不可用） - 文档ID: {doc_id}, 助手ID: {assistant_id or '未指定'}, 集合名称: {collection_name}, "
                f"MongoDB: {len(chunk_ids)} 个块"
            )
        elif qdrant_failed_count > 0:
            logger.warning(
                f"文档存储完成（部分失败） - 文档ID: {doc_id}, 助手ID: {assistant_id or '未指定'}, 集合名称: {collection_name}, "
                f"MongoDB: {len(chunk_ids)} 个块, "
                f"Qdrant: {qdrant_success_count} 成功, {qdrant_failed_count} 失败"
            )
        else:
            logger.info(
                f"文档存储完成 - 文档ID: {doc_id}, 助手ID: {assistant_id or '未指定'}, 集合名称: {collection_name}, "
                f"MongoDB: {len(chunk_ids)} 个块, "
                f"Qdrant: {qdrant_success_count} 个向量"
            )
        
        # 阶段6 (100%): 处理完成
        try:
            doc_repo.update_document_status(doc_id, "completed")
            doc_repo.update_document_progress(doc_id, 100, "完成", f"成功处理 {len(chunks)} 个文本块")
            logger.info(
                f"文档处理完成 - 文档ID: {doc_id}, 知识空间ID: {knowledge_space_id or '未指定'}, 集合名称: {collection_name}, 块数量: {len(chunks)}"
            )
        except Exception as e:
            logger.error(f"更新文档状态失败 - 文档ID: {doc_id}, 错误: {e}")
            
    except Exception as e:
        error_msg = f"文档处理失败 - 文档ID: {doc_id}, 错误: {str(e)}"
        logger.error(error_msg, exc_info=True)
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        try:
            doc_repo = get_document_repo()
            doc_repo.update_document_status(doc_id, "failed")
            doc_repo.update_document_progress(doc_id, 0, "失败", f"错误: {str(e)[:100]}")
        except Exception as update_error:
            logger.error(f"更新失败状态也失败 - 文档ID: {doc_id}, 错误: {update_error}")
        
        # 清理临时转换的PDF文件（即使处理失败也要清理）
        if 'converted_file_path' in locals() and converted_file_path and os.path.exists(converted_file_path):
            try:
                os.remove(converted_file_path)
                logger.info(f"已清理临时转换文件: {converted_file_path}")
            except Exception as cleanup_error:
                logger.warning(f"清理临时转换文件失败: {converted_file_path}, 错误: {str(cleanup_error)}")


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
        background_tasks.add_task(process_document_background, file_path, doc_id, assistant_id, knowledge_space_id)
        
        logger.info(f"文件上传成功，已启动后台处理任务 - 文档ID: {doc_id}, 助手ID: {assistant_id or '未指定'}, 文件哈希: {file_hash[:16]}...")
        
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "message": "文件上传成功，正在后台处理",
                "document_id": doc_id,
                "filename": file.filename,
                "file_size": file_size,
                "status": "processing"
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
        
        return DocumentProgressResponse(
            document_id=doc_id,
            progress_percentage=doc.get("progress_percentage", 0),
            current_stage=doc.get("current_stage", "未知"),
            stage_details=doc.get("stage_details", ""),
            status=doc.get("status", "unknown")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档进度失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档进度失败: {str(e)}"
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
        background_tasks.add_task(process_document_background, file_path, doc_id, assistant_id, knowledge_space_id)
        
        logger.info(f"文档重新处理任务已启动 - 文档ID: {doc_id}")
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "文档重新处理已启动",
                "document_id": doc_id,
                "status": "processing"
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
            for index, chunk in enumerate(filtered_chunks):
                chunk_id = str(chunk.get("_id") or chunk.get("id") or "")
                chunk_index = chunk.get("chunk_index")
                if target_chunk_id and chunk_id == target_chunk_id:
                    target_position = index
                    break
                if target_chunk_id:
                    continue
                if target_chunk_index is not None and chunk_index == target_chunk_index:
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
            target_chunk_id = target_chunk_id or str(target_chunk.get("_id") or target_chunk.get("id") or "")
            raw_target_index = target_chunk.get("chunk_index")
            target_chunk_index = raw_target_index if isinstance(raw_target_index, int) else target_chunk_index
        parse_quality = (doc.get("metadata") or {}).get("parse_quality")
        if not parse_quality and chunks:
            parse_quality = ((chunks[0].get("metadata") or {}).get("parse_summary") or None)

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
            media_type=media_type
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

