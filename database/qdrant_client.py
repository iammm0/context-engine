"""Qdrant向量数据库客户端封装模块"""
import os
import warnings
from typing import List, Optional, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue
)
import uuid
from utils.logger import logger


class QdrantVectorDB:
    """Qdrant向量数据库客户端封装"""
    
    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        collection_name: str = "advanced_rag_knowledge"
    ):
        """
        初始化Qdrant客户端
        
        Args:
            url: Qdrant服务地址，默认从环境变量获取
            api_key: API密钥（如果使用云服务）
            collection_name: 集合名称
        """
        self.url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.api_key = api_key or os.getenv("QDRANT_API_KEY")
        self.collection_name = collection_name
        
        # 处理 API key 与 HTTP 连接的安全警告
        # 如果使用本地 HTTP 连接，通常不需要 API key
        # 如果提供了 API key 但 URL 是 HTTP，则只在非本地地址时使用 API key
        use_api_key = self.api_key
        if use_api_key and self.url.startswith("http://"):
            # 检查是否是本地地址
            is_local = (
                "localhost" in self.url or 
                "127.0.0.1" in self.url or
                "::1" in self.url
            )
            if is_local:
                # 本地开发环境，不使用 API key 以避免警告
                logger.debug("检测到本地 HTTP 连接，忽略 API key（本地 Qdrant 通常不需要认证）")
                use_api_key = None
            else:
                # 非本地 HTTP 连接使用 API key 会触发警告，但允许继续
                logger.warning(
                    "使用 API key 与 HTTP 连接（不安全）。"
                    "建议在生产环境使用 HTTPS 连接或移除 API key。"
                )
        
        # 配置 Qdrant 客户端
        # 注意：httpx 在 Windows 上访问 localhost 会返回 502 错误
        # 解决方案：全面使用 gRPC 连接（端口 6334），完全避免使用 HTTP/httpx
        # gRPC 使用不同的协议栈，不依赖 httpx 库
        
        # 连接池和超时配置，优化高并发性能
        timeout = float(os.getenv("QDRANT_TIMEOUT", "30.0"))
        grpc_port = int(os.getenv("QDRANT_GRPC_PORT", "6334"))
        
        client_kwargs = {
            "url": self.url,
            "api_key": use_api_key,
            "check_compatibility": False,  # 跳过版本兼容性检查
            "timeout": timeout,  # 连接超时时间
            "prefer_grpc": True,  # 优先使用gRPC，性能更好，支持连接复用
        }
        
        # 对于所有 HTTP 连接，强制使用 gRPC 以避免 httpx 的 502 问题
        # gRPC支持连接复用，性能更好
        if self.url.startswith("http://"):
            # 使用 gRPC（端口 6334）而不是 HTTP（端口 6333）
            # gRPC 使用不同的协议，不依赖 httpx，支持连接复用
            grpc_url = self.url.replace(":6333", f":{grpc_port}").replace("http://", "")
            logger.info(f"使用 gRPC 连接 Qdrant（连接复用优化）: {grpc_url}, 超时: {timeout}s")
        elif self.url.startswith("https://"):
            # HTTPS 连接也优先使用 gRPC（如果支持）
            logger.info(f"使用 gRPC 连接 Qdrant（HTTPS，连接复用优化）, 超时: {timeout}s")
        else:
            # 其他格式（如 grpc://）直接使用
            logger.info(f"使用 gRPC 连接 Qdrant（连接复用优化）, 超时: {timeout}s")
        
        # 过滤 QdrantClient 关于 API key 与不安全连接的警告
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*Api key is used with an insecure connection.*", category=UserWarning)
            self.client = QdrantClient(**client_kwargs)
        
        # 测试连接（带重试）
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.debug(f"Testing Qdrant connection: {self.url} (attempt {attempt + 1}/{max_retries})")
                collections = self.client.get_collections()
                logger.info(f"✓ Qdrant connection successful, {len(collections.collections)} collections found")
                break
            except Exception as e:
                error_msg = str(e)
                if attempt < max_retries - 1:
                    logger.warning(f"Qdrant connection test failed (attempt {attempt + 1}): {error_msg[:100]}")
                    # 如果是连接错误，尝试使用 127.0.0.1 而不是 localhost
                    if ("localhost" in self.url or "502" in error_msg) and "127.0.0.1" not in self.url:
                        logger.info("Retrying with 127.0.0.1 instead of localhost...")
                        self.url = self.url.replace("localhost", "127.0.0.1")
                        client_kwargs["url"] = self.url
                        client_kwargs["prefer_grpc"] = True  # 确保使用 gRPC
                        # 过滤 QdrantClient 关于 API key 与不安全连接的警告
                        with warnings.catch_warnings():
                            warnings.filterwarnings("ignore", message=".*Api key is used with an insecure connection.*", category=UserWarning)
                            self.client = QdrantClient(**client_kwargs)
                else:
                    logger.warning(f"Qdrant connection test failed after {max_retries} attempts: {error_msg[:200]}")
                    logger.warning("The client will still be initialized, but operations may fail.")
                    # 不抛出异常，允许程序继续运行（优雅降级）
    
    def check_health(self) -> bool:
        """
        检查 Qdrant 服务是否可用
        
        Returns:
            bool: 如果服务可用返回 True，否则返回 False
        """
        try:
            # 尝试获取集合列表来检查服务是否可用
            self.client.get_collections()
            return True
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Qdrant 健康检查失败: {error_msg[:100]}")
            return False
    
    def create_collection(
        self,
        vector_size: int = 768,
        distance: Distance = Distance.COSINE
    ):
        """
        创建向量集合（如已存在则校验维度，必要时重建）
        
        Args:
            vector_size: 向量维度
            distance: 距离度量方式
        """
        try:
            # 如果集合已存在，先检查维度
            existing = self.client.get_collection(self.collection_name)
            existing_size = None
            try:
                # 单向量配置
                if hasattr(existing, "config") and hasattr(existing.config, "params"):
                    vec_cfg = existing.config.params.vectors
                    # 兼容单向量和多向量配置
                    if isinstance(vec_cfg, dict):
                        # 选择第一个向量配置
                        first_key = next(iter(vec_cfg))
                        existing_size = vec_cfg[first_key].size
                    elif hasattr(vec_cfg, "size"):
                        existing_size = vec_cfg.size
            except Exception:
                existing_size = None
            
            if existing_size and existing_size != vector_size:
                raise ValueError(
                    f"Qdrant 集合维度不匹配，集合 {self.collection_name} 现有维度 {existing_size}，"
                    f"请求维度 {vector_size}。为避免数据丢失，已禁止自动重建；请运行 scripts/reindex_collection.py 重建索引。"
                )
            else:
                # 已存在且维度匹配，直接返回
                if existing_size:
                    logger.info(f"Qdrant 集合已存在且维度匹配 ({existing_size})，跳过创建。")
                else:
                    # 无法识别维度时，仍尝试创建（若已存在会抛异常并被捕获）
                    self.client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=VectorParams(
                            size=vector_size,
                            distance=distance
                        )
                    )
        except Exception as e:
            # 集合不存在或其他原因导致 get_collection 失败，尝试直接创建
            if "not found" in str(e).lower() or "Collection does not exist" in str(e):
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=vector_size,
                        distance=distance
                    )
                )
            elif "already exists" in str(e).lower():
                # 已存在且无法检查维度时忽略
                logger.info("Qdrant 集合已存在，跳过创建。")
            else:
                raise
    
    def insert_vectors(
        self,
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
        ids: Optional[List[str]] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        插入向量数据（带重试机制）
        
        Args:
            vectors: 向量列表
            payloads: 元数据列表（包含chunk_id, document_id, text等）
            ids: 可选的ID列表，如果不提供则自动生成
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
        """
        import time
        
        if ids is None:
            # 生成 UUID 格式的 ID（gRPC 需要）
            ids = [uuid.uuid4() for _ in vectors]
        else:
            # 确保 ID 是 UUID 格式（如果是字符串，转换为 UUID）
            converted_ids = []
            for id_val in ids:
                if isinstance(id_val, str):
                    try:
                        converted_ids.append(uuid.UUID(id_val))
                    except ValueError:
                        # 如果不是有效的 UUID 字符串，生成新的 UUID
                        converted_ids.append(uuid.uuid4())
                else:
                    converted_ids.append(id_val)
            ids = converted_ids
        
        # 若存在维度不匹配，尝试在插入前自动重建集合
        current_dim = len(vectors[0]) if vectors else None
        if current_dim:
            try:
                existing = self.client.get_collection(self.collection_name)
                existing_size = None
                if hasattr(existing, "config") and hasattr(existing.config, "params"):
                    vec_cfg = existing.config.params.vectors
                    if isinstance(vec_cfg, dict):
                        first_key = next(iter(vec_cfg))
                        existing_size = vec_cfg[first_key].size
                    elif hasattr(vec_cfg, "size"):
                        existing_size = vec_cfg.size
                if existing_size and existing_size != current_dim:
                    raise ValueError(
                        f"Qdrant 集合维度不匹配，集合 {self.collection_name} 现有维度 {existing_size}，"
                        f"请求维度 {current_dim}。为避免数据丢失，已禁止自动重建；请运行 scripts/reindex_collection.py 重建索引。"
                    )
            except Exception:
                # 无法获取集合信息时忽略，后续插入可能失败但会进入重试
                pass
        
        points = [
            PointStruct(
                id=id_val,
                vector=vector,
                payload=payload
            )
            for id_val, vector, payload in zip(ids, vectors, payloads)
        ]
        
        # 重试机制
        last_exception = None
        for attempt in range(max_retries):
            try:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=points
                )
                # 成功插入，返回
                if attempt > 0:
                    logger.info(f"Qdrant 插入成功（第 {attempt + 1} 次尝试）")
                return
            except Exception as e:
                last_exception = e
                error_msg = str(e)
                
                # 如果是最后一次尝试，抛出异常
                if attempt == max_retries - 1:
                    logger.error(f"Qdrant 插入失败（已重试 {max_retries} 次）: {error_msg}")
                    raise
                
                # 维度错误：明确失败，不自动重建，避免清空用户数据
                if "vector dimension error" in error_msg.lower() or "expected dim" in error_msg.lower():
                    raise ValueError(
                        f"Qdrant 集合 {self.collection_name} 向量维度不匹配。"
                        "为避免数据丢失，已禁止自动重建；请运行 scripts/reindex_collection.py 重建索引。"
                    ) from e
                
                # 检查是否是临时性错误（502, 503, 504, timeout等）
                is_retryable = (
                    "502" in error_msg or
                    "503" in error_msg or
                    "504" in error_msg or
                    "timeout" in error_msg.lower() or
                    "connection" in error_msg.lower() or
                    "bad gateway" in error_msg.lower()
                )
                
                if is_retryable:
                    # 指数退避：延迟时间逐渐增加
                    delay = retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Qdrant 插入失败（第 {attempt + 1} 次尝试），{delay:.1f}秒后重试: {error_msg[:100]}"
                    )
                    time.sleep(delay)
                else:
                    # 非临时性错误，直接抛出
                    logger.error(f"Qdrant 插入失败（非临时性错误）: {error_msg}")
                    raise
        
        # 如果所有重试都失败，抛出最后一个异常
        if last_exception:
            raise last_exception
    
    def search(
        self,
        query_vector: List[float],
        limit: int = 5,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict[str, Any]] = None,
        query_text: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        向量相似度搜索
        
        Args:
            query_vector: 查询向量
            limit: 返回结果数量
            score_threshold: 相似度阈值
            filter_conditions: 过滤条件（如按document_id过滤）
            query_text: 原始查询文本（可选，用于Qdrant的query方法）
        
        Returns:
            搜索结果列表，包含score、payload等信息
        """
        query_filter = None
        if filter_conditions:
            conditions = []
            for key, value in filter_conditions.items():
                conditions.append(
                    FieldCondition(key=key, match=MatchValue(value=value))
                )
            query_filter = Filter(must=conditions)
        
        try:
            # 使用 query_points 方法（标准向量搜索 API）
            # query_points 可以直接接受向量作为 query 参数
            query_params = {
                "collection_name": self.collection_name,
                "query": query_vector,  # 直接传递向量
                "limit": limit,
                "query_filter": query_filter,
                "with_payload": True,
                "with_vectors": False,
            }
            
            if score_threshold is not None:
                query_params["score_threshold"] = score_threshold
            
            # 使用 query_points 进行向量搜索
            results = self.client.query_points(**query_params)
            
            # 转换结果格式
            return [
                {
                    "id": str(result.id),
                    "score": result.score,
                    "payload": result.payload
                }
                for result in results.points
            ]
        except Exception as e:
            error_msg = str(e)
            
            # 如果集合不存在，尝试自动创建
            if "not found" in error_msg.lower() or "doesn't exist" in error_msg.lower() or "Collection" in error_msg and "doesn't exist" in error_msg:
                logger.warning(f"Qdrant 集合不存在，尝试自动创建: {self.collection_name}")
                try:
                    # 使用查询向量的维度创建集合
                    vector_dim = len(query_vector)
                    self.create_collection(vector_size=vector_dim)
                    logger.info(f"已自动创建 Qdrant 集合: {self.collection_name}，向量维度: {vector_dim}")
                    
                    # 集合为空，返回空结果
                    return []
                except Exception as create_err:
                    logger.error(f"自动创建 Qdrant 集合失败: {create_err}", exc_info=True)
                    # 如果创建失败，返回空结果而不是抛出异常
                    return []
            
            logger.error(f"Qdrant 搜索失败: {error_msg}", exc_info=True)
            raise
    
    def delete_by_document_id(self, document_id: str):
        """根据文档ID删除所有相关向量"""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id)
                        )
                    ]
                )
            )
        except Exception as e:
            error_msg = str(e)
            # 如果集合不存在，忽略错误（没有数据可删除）
            if "not found" in error_msg.lower() or "doesn't exist" in error_msg.lower() or "Collection" in error_msg and "doesn't exist" in error_msg:
                logger.debug(f"集合不存在，跳过删除操作: {self.collection_name}")
                return
            # 其他错误重新抛出
            raise
    
    def delete_by_ids(self, ids: List[str]):
        """根据ID列表删除向量"""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=ids
        )
    
    def get_collection_info(self) -> Dict[str, Any]:
        """
        获取集合信息（包括向量数量等）
        
        Returns:
            包含集合信息的字典
        """
        try:
            collection_info = self.client.get_collection(self.collection_name)
            points_count = collection_info.points_count if hasattr(collection_info, 'points_count') else 0
            
            return {
                "points_count": points_count,
                "collection_name": self.collection_name
            }
        except Exception as e:
            error_msg = str(e)
            # 如果集合不存在，返回0
            if "not found" in error_msg.lower() or "doesn't exist" in error_msg.lower():
                return {
                    "points_count": 0,
                    "collection_name": self.collection_name
                }
            logger.warning(f"获取集合信息失败: {error_msg}")
            return {
                "points_count": 0,
                "collection_name": self.collection_name
            }
    
    def get_vectors_by_document_id(self, document_id: str) -> List[Dict[str, Any]]:
        """
        根据文档ID获取所有相关向量
        
        Args:
            document_id: 文档ID
        
        Returns:
            向量列表，包含id、vector、payload等信息
        """
        try:
            # 使用 scroll 方法获取所有匹配的向量
            scroll_filter = Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id)
                    )
                ]
            )
            
            # scroll 方法返回 (points, next_page_offset)
            points, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=scroll_filter,
                limit=10000,  # 设置一个较大的限制
                with_payload=True,
                with_vectors=True
            )
            
            result = []
            for point in points:
                point_dict = {
                    "id": str(point.id),
                    "payload": point.payload
                }
                # 检查是否有向量数据
                if hasattr(point, 'vector') and point.vector is not None:
                    point_dict["vector"] = point.vector
                else:
                    point_dict["vector"] = None
                result.append(point_dict)
            
            return result
        except Exception as e:
            error_msg = str(e)
            # 如果集合不存在，返回空列表（不记录警告，因为这是正常情况）
            if "not found" in error_msg.lower() or "doesn't exist" in error_msg.lower() or "Collection" in error_msg and "doesn't exist" in error_msg:
                return []
            # 其他错误记录警告
            logger.warning(f"获取文档向量失败 - 文档ID: {document_id}, 错误: {error_msg}")
            return []


# 全局Qdrant客户端实例（默认集合）
qdrant_client = QdrantVectorDB()
_QDRANT_CLIENT_CACHE: Dict[str, QdrantVectorDB] = {qdrant_client.collection_name: qdrant_client}


def get_qdrant_client(collection_name: str) -> QdrantVectorDB:
    """
    获取指定集合的Qdrant客户端实例
    
    Args:
        collection_name: 集合名称
    
    Returns:
        QdrantVectorDB实例
    """
    if collection_name in _QDRANT_CLIENT_CACHE:
        return _QDRANT_CLIENT_CACHE[collection_name]
    client = QdrantVectorDB(collection_name=collection_name)
    _QDRANT_CLIENT_CACHE[collection_name] = client
    return client
