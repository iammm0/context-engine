"""Document ingestion pipeline used by API dispatchers and Celery workers."""
from __future__ import annotations

import os
import traceback
from typing import Any, Dict, Optional

from chunking.router import ContentAnalyzer
from database.mongodb import ChunkRepository, DocumentRepository, mongodb_client
from database.qdrant_client import qdrant_client
from embedding.embedding_service import embedding_service
from parsers.parser_factory import ParserFactory
from parsers.router import ParsingRouter
from parsers.utils import ResultSynthesizer
from utils.chunk_metadata import (
    build_parse_quality_summary,
    build_retrieval_payload_metadata,
    enrich_chunks_for_visualization,
)
from utils.logger import logger

# Lazy repositories keep worker startup tolerant of temporarily unavailable MongoDB.
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
