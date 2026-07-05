"""MongoDB数据库连接（API服务使用）"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime
from pymongo import MongoClient
from utils.timezone import beijing_now
from pymongo.collection import Collection
from pymongo.database import Database
import os
from urllib.parse import urlparse

# 确保在导入时加载 .env 文件
try:
    from dotenv import load_dotenv
    # 尝试从当前目录和父目录加载 .env 文件
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path, override=False)
        print(f"[mongodb.py] [OK] 已加载 .env 文件: {env_path}")
    else:
        # 尝试从项目根目录加载
        root_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(root_env_path):
            load_dotenv(root_env_path, override=False)
            print(f"[mongodb.py] [OK] 已加载 .env 文件: {root_env_path}")
        else:
            # 使用默认的 load_dotenv()，会在当前目录和父目录中查找
            load_dotenv(override=False)
            print(f"[mongodb.py] [OK] 使用默认方式加载 .env 文件")
except ImportError:
    # 如果没有安装 python-dotenv，跳过
    print("[mongodb.py] [WARN] python-dotenv 未安装，无法加载 .env 文件")
    pass
except Exception as e:
    print(f"[mongodb.py] [WARN] 加载 .env 文件时出错: {str(e)}")
    pass


def parse_mongodb_uri(mongodb_uri: str) -> Tuple[str, str]:
    """
    解析MongoDB URI，提取连接字符串和数据库名称
    
    Args:
        mongodb_uri: MongoDB连接字符串，例如：
            - mongodb://localhost:27017/advanced_rag
            - mongodb://user:pass@localhost:27017/advanced_rag?authSource=admin
            - mongodb://localhost:27017/
    
    Returns:
        (connection_string, db_name): 连接字符串（不包含数据库名）和数据库名称
    """
    if not mongodb_uri:
        return "", ""
    
    # 解析URI
    parsed = urlparse(mongodb_uri)
    
    # 提取数据库名称（路径的第一部分）
    db_name = parsed.path.lstrip('/').split('/')[0] if parsed.path else ""
    
    # 如果没有数据库名称，使用默认值
    if not db_name:
        db_name = os.getenv("MONGODB_DB_NAME", "advanced_rag")
    
    # 构建不包含数据库名称的连接字符串
    # 保留认证信息、查询参数等
    if parsed.username and parsed.password:
        # 有认证信息
        auth_part = f"{parsed.username}:{parsed.password}@"
        connection_string = f"{parsed.scheme}://{auth_part}{parsed.hostname}"
        if parsed.port:
            connection_string += f":{parsed.port}"
        # 保留查询参数（如authSource）
        if parsed.query:
            connection_string += f"/?{parsed.query}"
        else:
            connection_string += "/"
    else:
        # 无认证信息
        connection_string = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port:
            connection_string += f":{parsed.port}"
        # 保留查询参数
        if parsed.query:
            connection_string += f"/?{parsed.query}"
        else:
            connection_string += "/"
    
    return connection_string, db_name


class MongoDB:
    """MongoDB异步客户端"""
    
    def __init__(self):
        self.client: AsyncIOMotorClient = None
        self.db = None
    
    async def connect(self):
        """建立连接"""
        mongodb_uri = os.getenv("MONGODB_URI")
        if mongodb_uri and mongodb_uri.strip():
            # 使用MONGODB_URI，解析连接字符串和数据库名称
            connection_string, db_name = parse_mongodb_uri(mongodb_uri)
        else:
            # 使用单独的环境变量构建连接字符串
            host = os.getenv("MONGODB_HOST", "localhost")
            port = os.getenv("MONGODB_PORT", "27017")
            username = os.getenv("MONGODB_USERNAME")
            password = os.getenv("MONGODB_PASSWORD")
            auth_source = os.getenv("MONGODB_AUTH_SOURCE", "admin")
            
            if username and password:
                # 有认证信息的连接字符串
                connection_string = f"mongodb://{username}:{password}@{host}:{port}/?authSource={auth_source}"
            else:
                # 无认证连接字符串
                connection_string = f"mongodb://{host}:{port}/"
            
            db_name = os.getenv("MONGODB_DB_NAME", "advanced_rag")
        
        # 配置连接池参数，优化高并发性能
        # maxPoolSize: 每个worker的最大连接数（建议100-200）
        # minPoolSize: 最小连接池大小（保持一定数量的连接）
        # maxIdleTimeMS: 连接空闲超时时间（30秒）
        # serverSelectionTimeoutMS: 服务器选择超时（5秒）
        # connectTimeoutMS: 连接超时（10秒）
        # socketTimeoutMS: socket超时（30秒）
        pool_options = {
            "maxPoolSize": int(os.getenv("MONGODB_MAX_POOL_SIZE", "100")),
            "minPoolSize": int(os.getenv("MONGODB_MIN_POOL_SIZE", "10")),
            "maxIdleTimeMS": int(os.getenv("MONGODB_MAX_IDLE_TIME_MS", "30000")),
            "serverSelectionTimeoutMS": int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "5000")),
            "connectTimeoutMS": int(os.getenv("MONGODB_CONNECT_TIMEOUT_MS", "10000")),
            "socketTimeoutMS": int(os.getenv("MONGODB_SOCKET_TIMEOUT_MS", "30000")),
        }
        
        # 如果连接字符串中已有查询参数，需要合并
        if "?" in connection_string:
            # 解析现有查询参数
            base_uri, existing_params = connection_string.split("?", 1)
            # 添加连接池参数
            params_list = [existing_params] if existing_params else []
            for key, value in pool_options.items():
                params_list.append(f"{key}={value}")
            connection_string = f"{base_uri}?{'&'.join(params_list)}"
        else:
            # 没有查询参数，直接添加
            params_list = [f"{key}={value}" for key, value in pool_options.items()]
            connection_string = f"{connection_string}?{'&'.join(params_list)}"
        
        from utils.logger import logger
        
        try:
            self.client = AsyncIOMotorClient(connection_string)
            self.db = self.client[db_name]
            
            # 启动时 ping 校验，确保连接可用（Motor 惰性连接，首次操作才真正连）
            await self.db.command("ping")
            
            logger.info(
                f"MongoDB连接池配置 - maxPoolSize: {pool_options['maxPoolSize']}, "
                f"minPoolSize: {pool_options['minPoolSize']}, "
                f"数据库: {db_name}"
            )
            logger.info("MongoDB 连接成功")
            return self.db
        except Exception as e:
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None
                self.db = None
            err_msg = str(e).strip()
            hint = (
                "请确认：1) MongoDB 服务已启动；"
                "2) .env 中 MONGODB_URI（或 MONGODB_HOST/PORT）配置正确；"
                "3) 若使用 Docker，宿主机请用 host.docker.internal 或 127.0.0.1。"
            )
            logger.error(f"MongoDB 连接失败: {err_msg}")
            logger.error(hint)
            raise RuntimeError(f"MongoDB 连接失败: {err_msg}\n{hint}") from e
    
    async def disconnect(self):
        """关闭连接"""
        if self.client:
            self.client.close()

    async def ensure_connected(self):
        """若未连接则建立连接（用于请求级兜底，启动时连接失败后首次请求可重试）"""
        if self.db is None:
            await self.connect()
    
    def get_collection(self, collection_name: str) -> AsyncIOMotorCollection:
        """获取集合"""
        if self.db is None:
            raise RuntimeError("数据库未连接，请先调用connect()")
        return self.db[collection_name]


# 全局数据库实例
mongodb = MongoDB()


async def require_mongodb():
    """
    供 FastAPI Depends 使用：确保 MongoDB 已连接。
    启动时若连接失败，在首次请求时会重试一次；若仍失败则返回 503。
    """
    if mongodb.db is None:
        try:
            await mongodb.ensure_connected()
        except Exception as e:
            from utils.logger import logger
            logger.error(f"MongoDB 连接失败: {e}")
            from fastapi import HTTPException
            raise HTTPException(
                status_code=503,
                detail="数据库暂时不可用，请稍后重试。请确认 MongoDB 已启动且 .env 配置正确。",
            )


def get_user_collection() -> AsyncIOMotorCollection:
    """获取用户集合"""
    return mongodb.get_collection("users")


# ========== 同步MongoDB客户端（用于文档和chunk操作） ==========

class MongoDBClient:
    """MongoDB客户端封装类（同步版本，用于文档处理）"""
    
    def __init__(self, connection_string: Optional[str] = None):
        """
        初始化MongoDB客户端
        
        Args:
            connection_string: MongoDB连接字符串，默认从环境变量获取
        """
        from utils.logger import logger
        logger.debug("初始化 MongoDBClient...")
        if connection_string:
            self.connection_string, self.db_name = parse_mongodb_uri(connection_string)
            logger.debug(f"使用传入的连接字符串（长度: {len(connection_string)}）")
        else:
            # 优先使用MONGODB_URI环境变量
            mongodb_uri = os.getenv("MONGODB_URI")
            logger.debug(f"MONGODB_URI 环境变量值: {mongodb_uri[:50] + '...' if mongodb_uri and len(mongodb_uri) > 50 else mongodb_uri}")
            if mongodb_uri and mongodb_uri.strip():
                self.connection_string, self.db_name = parse_mongodb_uri(mongodb_uri)
                logger.info(f"✓ 使用环境变量 MONGODB_URI")
            else:
                # 使用单独的环境变量构建连接字符串
                host = os.getenv("MONGODB_HOST", "localhost")
                port = os.getenv("MONGODB_PORT", "27017")
                username = os.getenv("MONGODB_USERNAME")
                password = os.getenv("MONGODB_PASSWORD")
                auth_source = os.getenv("MONGODB_AUTH_SOURCE", "admin")
                
                if username and password:
                    self.connection_string = f"mongodb://{username}:{password}@{host}:{port}/?authSource={auth_source}"
                else:
                    self.connection_string = f"mongodb://{host}:{port}/"
                
                self.db_name = os.getenv("MONGODB_DB_NAME", "advanced_rag")
                logger.info(f"✓ 使用单独的环境变量构建连接字符串")
        
        logger.debug(f"数据库名称: {self.db_name}")
        self.client: Optional[MongoClient] = None
        self.db: Optional[Database] = None
    
    def connect(self):
        """建立同步连接"""
        from utils.logger import logger
        # 记录连接信息（隐藏密码）
        safe_uri = self.connection_string
        if "@" in safe_uri:
            # 隐藏密码部分
            parts = safe_uri.split("@")
            if len(parts) == 2:
                auth_part = parts[0].split("://")[1] if "://" in parts[0] else parts[0]
                if ":" in auth_part:
                    username = auth_part.split(":")[0]
                    safe_uri = safe_uri.replace(auth_part, f"{username}:***")
        
        logger.info(f"开始建立 MongoDB 连接")
        logger.info(f"连接字符串: {safe_uri}")
        logger.info(f"目标数据库: {self.db_name}")
        
        try:
            logger.debug("创建 MongoClient 实例...")
            self.client = MongoClient(self.connection_string)
            logger.debug("MongoClient 实例创建成功")
            
            logger.debug(f"获取数据库对象: {self.db_name}")
            self.db = self.client[self.db_name]
            logger.debug(f"数据库对象获取成功: {self.db}")
            
            # 测试连接（使用当前数据库，避免需要 listDatabases 权限）
            logger.debug("执行 ping 命令测试连接...")
            try:
                ping_result = self.db.command('ping')
                logger.debug(f"Ping 结果: {ping_result}")
                logger.info("✓ MongoDB ping 成功")
            except Exception as ping_error:
                logger.warning(f"Ping 失败，但继续连接: {str(ping_error)}")
            
            # 尝试检查集合是否存在（如果失败也不影响连接）
            try:
                logger.debug(f"检查集合 documents 是否存在...")
                collection_list = self.db.list_collection_names()
                logger.debug(f"数据库 {self.db_name} 中的集合: {collection_list}")
                logger.info(f"MongoDB连接成功 - 数据库: {self.db_name}, 集合数量: {len(collection_list)}")
            except Exception as list_error:
                logger.warning(f"无法列出集合（可能需要权限）: {str(list_error)}")
                logger.info(f"MongoDB连接成功 - 数据库: {self.db_name}（无法列出集合）")
            return self.db
        except Exception as e:
            logger.error(f"MongoDB连接失败: {str(e)}", exc_info=True)
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"连接字符串（前50字符）: {self.connection_string[:50]}...")
            raise
    
    def get_collection(self, collection_name: str) -> Collection:
        """获取集合对象"""
        if self.db is None:
            self.connect()
        return self.db[collection_name]
    
    def close(self):
        """关闭连接"""
        if self.client:
            self.client.close()


class DocumentRepository:
    """文档元数据仓库"""
    
    def __init__(self, mongodb_client: MongoDBClient):
        from utils.logger import logger
        logger.debug("初始化 DocumentRepository...")
        self.collection = mongodb_client.get_collection("documents")
        logger.debug(f"DocumentRepository 初始化完成 - 集合: {self.collection.name}")
    
    def find_duplicate_by_hash(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """
        根据文件哈希查找重复文档
        
        Args:
            file_hash: 文件哈希值
        
        Returns:
            如果找到重复文档，返回文档信息；否则返回 None
        """
        doc = self.collection.find_one({"file_hash": file_hash})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
    
    def create_document(
        self,
        title: str,
        file_type: str,
        file_path: str,
        file_size: int,
        file_hash: str,
        metadata: Optional[Dict[str, Any]] = None,
        assistant_id: Optional[str] = None,
        knowledge_space_id: Optional[str] = None,
    ) -> str:
        """
        创建文档记录
        
        Args:
            title: 文档标题
            file_type: 文件类型
            file_path: 文件路径
            file_size: 文件大小
            file_hash: 文件哈希值（用于重复检查）
            metadata: 元数据
        
        Returns:
            文档ID
        """
        doc = {
            "title": title,
            "file_type": file_type,
            "file_path": file_path,
            "file_size": file_size,
            "file_hash": file_hash,  # 文件哈希，用于重复检查
            "metadata": metadata or {},
            # 兼容字段：assistant_id（历史）；新字段：knowledge_space_id（知识空间）
            "assistant_id": assistant_id,
            "knowledge_space_id": knowledge_space_id or assistant_id,
            "created_at": beijing_now(),
            "updated_at": beijing_now(),
            "status": "processing",  # processing, completed, failed
            "progress_percentage": 0,  # 0-100
            "current_stage": "文档上传",  # 当前阶段名称
            "stage_details": ""  # 阶段详细信息
        }
        result = self.collection.insert_one(doc)
        return str(result.inserted_id)
    
    def update_document_status(self, doc_id: str, status: str):
        """更新文档状态"""
        from bson import ObjectId
        from utils.logger import logger
        try:
            # 确保 doc_id 是 ObjectId 格式
            if isinstance(doc_id, str):
                doc_id = ObjectId(doc_id)
            
            result = self.collection.update_one(
                {"_id": doc_id},
                {"$set": {"status": status, "updated_at": beijing_now()}}
            )
            
            # 记录更新结果
            if result.modified_count == 0:
                logger.warning(f"更新文档状态失败 - 文档ID: {doc_id}, 状态: {status}, 未找到文档或无需更新")
            else:
                logger.info(f"✓ 文档状态已更新 - 文档ID: {doc_id}, 状态: {status}")
        except Exception as e:
            logger.error(f"更新文档状态异常 - 文档ID: {doc_id}, 状态: {status}, 错误: {e}", exc_info=True)
            raise
    
    def update_document_progress(
        self,
        doc_id: str,
        progress_percentage: int,
        current_stage: str,
        stage_details: str = ""
    ):
        """
        更新文档处理进度
        
        Args:
            doc_id: 文档ID
            progress_percentage: 进度百分比 (0-100)
            current_stage: 当前阶段名称
            stage_details: 阶段详细信息（如"向量化 50/100"）
        """
        from bson import ObjectId
        from utils.logger import logger
        try:
            # 确保 doc_id 是 ObjectId 格式
            if isinstance(doc_id, str):
                doc_id = ObjectId(doc_id)
            
            result = self.collection.update_one(
                {"_id": doc_id},
                {
                    "$set": {
                        "progress_percentage": max(0, min(100, progress_percentage)),
                        "current_stage": current_stage,
                        "stage_details": stage_details,
                        "updated_at": beijing_now()
                    }
                }
            )
            
            # 记录更新结果
            if result.modified_count == 0:
                logger.warning(
                    f"更新文档进度失败 - 文档ID: {doc_id}, 进度: {progress_percentage}%, "
                    f"阶段: {current_stage}, 未找到文档或无需更新"
                )
            else:
                # 只在重要阶段记录日志（避免日志过多）
                if progress_percentage == 100 or progress_percentage % 25 == 0:
                    logger.info(
                        f"文档进度已更新 - 文档ID: {doc_id}, 进度: {progress_percentage}%, "
                        f"阶段: {current_stage}, 详情: {stage_details}"
                    )
        except Exception as e:
            logger.error(
                f"更新文档进度异常 - 文档ID: {doc_id}, 进度: {progress_percentage}%, "
                f"阶段: {current_stage}, 错误: {e}", exc_info=True
            )
            raise
    
    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """获取文档信息"""
        from bson import ObjectId
        try:
            # 确保 doc_id 是 ObjectId 格式
            if isinstance(doc_id, str):
                doc_id = ObjectId(doc_id)
            
            doc = self.collection.find_one({"_id": doc_id})
            if doc:
                doc["_id"] = str(doc["_id"])
            return doc
        except Exception as e:
            from utils.logger import logger
            logger.error(f"获取文档失败 - 文档ID: {doc_id}, 错误: {e}")
            return None
    
    def list_documents(
        self,
        skip: int = 0,
        limit: int = 100,
        assistant_id: Optional[str] = None,
        knowledge_space_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出所有文档"""
        from utils.logger import logger
        logger.info(
            f"开始查询文档列表 - skip: {skip}, limit: {limit}, assistant_id: {assistant_id}, knowledge_space_id: {knowledge_space_id}"
        )
        logger.debug(f"使用集合: {self.collection.name}, 数据库: {self.collection.database.name}")
        
        try:
            # 记录查询前的状态
            logger.debug("准备执行 MongoDB find 查询")
            query = {}
            # 优先按 knowledge_space_id 过滤
            if knowledge_space_id:
                query["knowledge_space_id"] = knowledge_space_id
            elif assistant_id:
                # 向后兼容
                query["assistant_id"] = assistant_id
            docs = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
            logger.debug(f"MongoDB 查询对象已创建，开始迭代结果")
            
            result_list = []
            doc_count = 0
            for doc in docs:
                doc_count += 1
                try:
                    processed_doc = {**doc, "_id": str(doc["_id"])}
                    result_list.append(processed_doc)
                    if doc_count <= 3:  # 只记录前3个文档的详细信息
                        logger.debug(f"处理文档 {doc_count}: id={doc.get('_id')}, title={doc.get('title', 'N/A')}")
                except Exception as e:
                    logger.warning(f"处理文档时出错 (文档 {doc_count}): {str(e)}")
                    continue
            
            logger.info(f"文档列表查询完成 - 返回 {len(result_list)} 条记录")
            return result_list
        except Exception as e:
            logger.error(f"查询文档列表失败: {str(e)}", exc_info=True)
            logger.error(f"错误类型: {type(e).__name__}")
            raise
    
    def count_documents(self, assistant_id: Optional[str] = None, knowledge_space_id: Optional[str] = None) -> int:
        """统计文档总数"""
        try:
            query = {}
            if knowledge_space_id:
                query["knowledge_space_id"] = knowledge_space_id
            elif assistant_id:
                query["assistant_id"] = assistant_id
            return self.collection.count_documents(query)
        except Exception as e:
            from utils.logger import logger
            logger.error(f"统计文档总数失败: {str(e)}", exc_info=True)
            raise
    
    def count_documents_by_assistants(self, assistant_ids: List[str]) -> int:
        """统计多个助手的文档总数"""
        try:
            if not assistant_ids:
                return 0
            query = {"assistant_id": {"$in": assistant_ids}}
            return self.collection.count_documents(query)
        except Exception as e:
            from utils.logger import logger
            logger.error(f"统计多个助手的文档总数失败: {str(e)}", exc_info=True)
            raise
    
    def update_document_title(self, doc_id: str, title: str):
        """更新文档标题"""
        from bson import ObjectId
        from utils.logger import logger
        try:
            # 确保 doc_id 是 ObjectId 格式
            if isinstance(doc_id, str):
                doc_id = ObjectId(doc_id)
            
            result = self.collection.update_one(
                {"_id": doc_id},
                {"$set": {"title": title, "updated_at": beijing_now()}}
            )
            
            # 记录更新结果
            if result.modified_count == 0:
                logger.warning(f"更新文档标题失败 - 文档ID: {doc_id}, 标题: {title}, 未找到文档或无需更新")
            else:
                logger.info(f"✓ 文档标题已更新 - 文档ID: {doc_id}, 标题: {title}")
        except Exception as e:
            logger.error(f"更新文档标题异常 - 文档ID: {doc_id}, 标题: {title}, 错误: {e}", exc_info=True)
            raise

    def update_document_metadata(self, doc_id: str, metadata_patch: Dict[str, Any]):
        """合并更新文档元数据。"""
        from bson import ObjectId
        from utils.logger import logger
        try:
            if isinstance(doc_id, str):
                doc_id = ObjectId(doc_id)

            set_fields = {
                f"metadata.{key}": value
                for key, value in (metadata_patch or {}).items()
            }
            if not set_fields:
                return
            set_fields["updated_at"] = beijing_now()

            result = self.collection.update_one(
                {"_id": doc_id},
                {"$set": set_fields},
            )
            if result.modified_count == 0:
                logger.warning(f"更新文档元数据失败 - 文档ID: {doc_id}, 未找到文档或无需更新")
            else:
                logger.info(f"✓ 文档元数据已更新 - 文档ID: {doc_id}, 字段: {list(metadata_patch.keys())}")
        except Exception as e:
            logger.error(f"更新文档元数据异常 - 文档ID: {doc_id}, 错误: {e}", exc_info=True)
            raise
    
    def delete_document(self, doc_id: str) -> bool:
        """
        删除文档
        
        Args:
            doc_id: 文档ID
        
        Returns:
            bool: 如果成功删除返回True，否则返回False
        """
        from bson import ObjectId
        try:
            # 确保 doc_id 是 ObjectId 格式
            if isinstance(doc_id, str):
                doc_id = ObjectId(doc_id)
            
            result = self.collection.delete_one({"_id": doc_id})
            return result.deleted_count > 0
        except Exception as e:
            from utils.logger import logger
            logger.error(f"删除文档失败 - 文档ID: {doc_id}, 错误: {e}")
            return False

    def move_document(self, doc_id: str, new_assistant_id: str) -> Optional[Dict[str, Any]]:
        """
        移动文档到新的助手（更新assistant_id）

        Args:
            doc_id: 文档ID
            new_assistant_id: 新的助手ID

        Returns:
            如果移动成功，返回包含文档信息的字典；否则返回None
        """
        from utils.logger import logger
        from bson import ObjectId
        try:
            # 确保 doc_id 是 ObjectId 格式
            if isinstance(doc_id, str):
                doc_id = ObjectId(doc_id)
            
            # 获取文档信息
            doc = self.collection.find_one({"_id": doc_id})
            if not doc:
                logger.warning(f"文档不存在，无法移动 - 文档ID: {doc_id}")
                return None
            
            old_assistant_id = doc.get("assistant_id")
            
            # 更新文档的assistant_id
            result = self.collection.update_one(
                {"_id": doc_id},
                {"$set": {"assistant_id": new_assistant_id, "updated_at": beijing_now()}}
            )
            
            if result.modified_count == 0:
                logger.warning(f"移动文档失败 - 文档ID: {doc_id}, 新助手ID: {new_assistant_id}, 未找到文档或无需更新")
                return None
            
            logger.info(f"文档移动成功 - 文档ID: {doc_id}, 原助手ID: {old_assistant_id}, 新助手ID: {new_assistant_id}")
            
            # 返回更新后的文档信息
            updated_doc = self.collection.find_one({"_id": doc_id})
            if updated_doc:
                updated_doc["_id"] = str(updated_doc["_id"])
            return updated_doc
            
        except Exception as e:
            logger.error(f"移动文档失败 - 文档ID: {doc_id}, 新助手ID: {new_assistant_id}, 错误: {str(e)}", exc_info=True)
            return None

    def transfer_to_resource(self, doc_id: str, assistant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        将文档转换为资源（用于资源社区分享）

        Args:
            doc_id: 文档ID
            assistant_id: 目标助手ID

        Returns:
            如果转换成功，返回包含资源ID和文档信息的字典；否则返回None
        """
        from utils.logger import logger
        try:
            # 获取文档信息
            doc = self.get_document(doc_id)
            if not doc:
                logger.warning(f"文档不存在，无法转换为资源 - 文档ID: {doc_id}")
                return None

            # 检查文档是否已经是资源（通过file_path检查）
            resource_repo = None
            try:
                from database.mongodb import MongoDBClient
                mongodb_client = MongoDBClient()
                mongodb_client.connect()
                resource_repo = ResourceRepository(mongodb_client)
            except Exception as e:
                logger.error(f"无法初始化资源仓库: {str(e)}")
                return None

            # 检查是否已存在相同的资源
            existing_resources = resource_repo.collection.find_one({
                "file_path": doc["file_path"],
                "assistant_id": assistant_id
            })
            if existing_resources:
                # 确保已存在的资源也是公开状态
                from bson import ObjectId
                existing_resource_id = existing_resources["_id"]
                if isinstance(existing_resource_id, str):
                    existing_resource_id = ObjectId(existing_resource_id)
                
                # 更新已存在资源的状态，确保它是公开的
                resource_repo.collection.update_one(
                    {"_id": existing_resource_id},
                    {"$set": {
                        "is_public": True,
                        "status": "active",
                        "updated_at": beijing_now()
                    }}
                )
                
                logger.info(f"文档已存在于资源社区 - 文档ID: {doc_id}, 资源ID: {existing_resources['_id']}, 已更新为公开状态")
                return {
                    "resource_id": str(existing_resources["_id"]),
                    "document": doc,
                    "already_exists": True
                }

            # 获取文件大小
            import os
            file_size = 0
            if os.path.exists(doc["file_path"]):
                file_size = os.path.getsize(doc["file_path"])

            # 从文件名提取文件类型
            file_name = os.path.basename(doc["file_path"])
            file_ext = os.path.splitext(file_name)[1].lower()
            file_type = file_ext[1:] if file_ext else ""

            # 创建资源记录（直接在创建时设置公开状态）
            resource_id_str = resource_repo.create_resource(
                title=doc["title"],
                description=doc.get("title", file_name),  # 使用文档标题作为描述
                file_path=doc["file_path"],
                file_type=file_type,
                file_size=file_size,
                assistant_id=assistant_id
            )

            # 转换 resource_id 为 ObjectId
            from bson import ObjectId
            resource_id = ObjectId(resource_id_str)

            # 更新资源为公开状态和active状态（确保设置）
            update_result = resource_repo.collection.update_one(
                {"_id": resource_id},
                {"$set": {
                    "is_public": True,
                    "status": "active",
                    "updated_at": beijing_now()
                }}
            )
            
            if update_result.modified_count == 0:
                logger.warning(f"更新资源状态失败 - 资源ID: {resource_id_str}, 可能资源不存在或字段已存在")
            else:
                logger.info(f"资源已设置为公开状态 - 资源ID: {resource_id_str}, is_public=True, status=active")

            # 添加上传者信息
            if "uploader_id" in doc:
                uploader_update_result = resource_repo.collection.update_one(
                    {"_id": resource_id},
                    {"$set": {
                        "uploader_id": doc["uploader_id"],
                        "uploader_username": doc.get("uploader_username"),
                        "uploader_name": doc.get("uploader_name")
                    }}
                )
                if uploader_update_result.modified_count > 0:
                    logger.info(f"已添加上传者信息 - 资源ID: {resource_id_str}, 上传者ID: {doc.get('uploader_id')}")

            logger.info(f"文档成功转换为资源 - 文档ID: {doc_id}, 资源ID: {resource_id_str}")
            return {
                "resource_id": resource_id_str,
                "document": doc,
                "already_exists": False
            }

        except Exception as e:
            logger.error(f"文档转换为资源失败 - 文档ID: {doc_id}, 错误: {str(e)}", exc_info=True)
            return None


class ChunkRepository:
    """文档分块仓库"""
    
    def __init__(self, mongodb_client: MongoDBClient):
        self.collection = mongodb_client.get_collection("chunks")
    
    def create_chunk(
        self,
        document_id: str,
        chunk_index: int,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        创建文档块记录
        
        Returns:
            块ID
        """
        chunk = {
            "document_id": document_id,
            "chunk_index": chunk_index,
            "text": text,
            "metadata": metadata or {},
            "created_at": beijing_now()
        }
        result = self.collection.insert_one(chunk)
        return str(result.inserted_id)
    
    def get_chunks_by_document(self, document_id: str) -> List[Dict[str, Any]]:
        """获取文档的所有块"""
        chunks = self.collection.find({"document_id": document_id}).sort("chunk_index", 1)
        return [{**chunk, "_id": str(chunk["_id"])} for chunk in chunks]

    def get_chunk_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """按 chunk_id 获取单个块（用于邻居扩展）"""
        try:
            from bson import ObjectId
            doc = self.collection.find_one({"_id": ObjectId(chunk_id)})
            if not doc:
                return None
            return {**doc, "_id": str(doc["_id"])}
        except Exception:
            return None

    def get_chunks_by_indices(self, document_id: str, indices: List[int]) -> List[Dict[str, Any]]:
        """按 chunk_index 列表批量获取块（用于邻居扩展）"""
        if not indices:
            return []
        docs = self.collection.find({"document_id": document_id, "chunk_index": {"$in": indices}})
        # 返回顺序按 chunk_index 排序，方便拼上下文
        items = [{**d, "_id": str(d["_id"])} for d in docs]
        items.sort(key=lambda x: x.get("chunk_index", 0))
        return items

    def get_neighbor_chunks(self, document_id: str, chunk_index: int, window: int = 1) -> List[Dict[str, Any]]:
        """获取指定 chunk 的前后邻居块（含自身）"""
        start = max(0, int(chunk_index) - int(window))
        end = int(chunk_index) + int(window)
        indices = list(range(start, end + 1))
        return self.get_chunks_by_indices(document_id, indices)
    
    def delete_chunks_by_document(self, document_id: str):
        """删除文档的所有块"""
        self.collection.delete_many({"document_id": document_id})


class ResourceRepository:
    """资源仓库"""
    
    def __init__(self, mongodb_client: MongoDBClient):
        from utils.logger import logger
        logger.debug("初始化 ResourceRepository...")
        self.collection = mongodb_client.get_collection("resources")
        logger.debug(f"ResourceRepository 初始化完成 - 集合: {self.collection.name}")
    
    def create_resource(
        self,
        title: str,
        description: str,
        file_path: Optional[str] = None,
        file_type: str = "",
        file_size: int = 0,
        assistant_id: Optional[str] = None,
        url: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        创建资源记录
        
        Args:
            title: 资源标题
            description: 资源描述（用于向量检索）
            file_path: 文件路径（可选，外部链接资源可能没有）
            file_type: 文件类型
            file_size: 文件大小
            assistant_id: 关联的助手ID
            url: 外部链接URL（可选）
            tags: 标签列表（可选）
        
        Returns:
            资源ID
        """
        resource = {
            "title": title,
            "description": description,
            "file_type": file_type,
            "file_size": file_size,
            "assistant_id": assistant_id,
            "schema_version": 2,  # 当前版本
            "created_at": beijing_now(),
            "updated_at": beijing_now()
        }
        
        # 可选字段
        if file_path is not None:
            resource["file_path"] = file_path
        if url:
            resource["url"] = url
        if tags:
            resource["tags"] = tags
        
        result = self.collection.insert_one(resource)
        return str(result.inserted_id)
    
    def get_resource(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """获取资源信息（自动进行版本兼容和迁移）"""
        from bson import ObjectId
        try:
            if isinstance(resource_id, str):
                resource_id = ObjectId(resource_id)
            
            resource = self.collection.find_one({"_id": resource_id})
            if resource:
                resource["_id"] = str(resource["_id"])
                # 自动迁移旧版本资源
                resource = self._migrate_resource_if_needed(resource, resource_id)
            return resource
        except Exception as e:
            from utils.logger import logger
            logger.error(f"获取资源失败 - 资源ID: {resource_id}, 错误: {e}")
            return None
    
    def _migrate_resource_if_needed(self, resource: Dict[str, Any], resource_id) -> Dict[str, Any]:
        """
        检查并迁移旧版本资源数据
        
        Args:
            resource: 资源数据字典
            resource_id: 资源ID（ObjectId或str）
        
        Returns:
            迁移后的资源数据
        """
        from utils.logger import logger
        from bson import ObjectId
        
        # 获取当前版本（默认为1，表示旧版本）
        current_version = resource.get("schema_version", 1)
        target_version = 2
        
        # 如果已经是当前版本，直接返回
        if current_version >= target_version:
            return resource
        
        logger.info(f"检测到旧版本资源 (v{current_version})，开始迁移: {resource.get('title', 'Unknown')}")
        
        # 执行版本迁移
        migrated_resource = self._migrate_from_v1_to_v2(resource)
        
        # 更新数据库中的资源
        try:
            # 确保resource_id是ObjectId类型
            if isinstance(resource_id, str):
                resource_id = ObjectId(resource_id)
            
            update_fields = {
                "schema_version": target_version,
                "updated_at": beijing_now()
            }
            
            # 添加缺失的字段
            if "status" not in migrated_resource:
                update_fields["status"] = "active"
            if "is_public" not in migrated_resource:
                update_fields["is_public"] = True
            if "tags" not in migrated_resource or migrated_resource["tags"] is None:
                update_fields["tags"] = []
            if "uploader_id" not in migrated_resource:
                update_fields["uploader_id"] = None
            if "thumbnail_url" not in migrated_resource:
                update_fields["thumbnail_url"] = None
            
            # 更新数据库
            self.collection.update_one(
                {"_id": resource_id},
                {"$set": update_fields}
            )
            
            # 更新返回的资源数据
            migrated_resource.update(update_fields)
            logger.info(f"资源迁移完成: {resource.get('title', 'Unknown')} (v{current_version} -> v{target_version})")
            
        except Exception as e:
            logger.error(f"更新资源版本失败: {str(e)}", exc_info=True)
        
        return migrated_resource
    
    def _migrate_from_v1_to_v2(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """
        从v1迁移到v2
        
        v1版本可能缺少的字段：
        - status (默认: "active")
        - is_public (默认: True)
        - tags (默认: [])
        - uploader_id (默认: None)
        - thumbnail_url (默认: None)
        - schema_version (默认: 1)
        
        v2版本新增字段：
        - schema_version: 2
        - 所有字段都有默认值
        """
        migrated = resource.copy()
        
        # 设置默认值
        if "status" not in migrated:
            migrated["status"] = "active"
        
        if "is_public" not in migrated:
            migrated["is_public"] = True
        
        if "tags" not in migrated:
            migrated["tags"] = []
        elif migrated["tags"] is None:
            migrated["tags"] = []
        
        if "uploader_id" not in migrated:
            migrated["uploader_id"] = None
        
        if "thumbnail_url" not in migrated:
            migrated["thumbnail_url"] = None
        
        migrated["schema_version"] = 2
        
        return migrated
    
    def list_resources(
        self, 
        skip: int = 0, 
        limit: int = 100, 
        assistant_id: Optional[str] = None,
        status: Optional[str] = None,
        is_public: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """列出所有资源"""
        from utils.logger import logger
        logger.info(f"开始查询资源列表 - skip: {skip}, limit: {limit}, assistant_id: {assistant_id}, status: {status}, is_public: {is_public}")
        
        try:
            query = {}
            if assistant_id:
                query["assistant_id"] = assistant_id
            if status:
                query["status"] = status
            if is_public is not None:
                query["is_public"] = is_public
            resources = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
            
            result_list = []
            for resource in resources:
                try:
                    resource_id = resource["_id"]
                    processed_resource = {**resource, "_id": str(resource_id)}
                    # 自动迁移旧版本资源
                    processed_resource = self._migrate_resource_if_needed(processed_resource, resource_id)
                    result_list.append(processed_resource)
                except Exception as e:
                    logger.warning(f"处理资源时出错: {str(e)}")
                    continue
            
            logger.info(f"资源列表查询完成 - 返回 {len(result_list)} 条记录")
            return result_list
        except Exception as e:
            logger.error(f"查询资源列表失败: {str(e)}", exc_info=True)
            raise
    
    def count_resources(
        self, 
        assistant_id: Optional[str] = None,
        status: Optional[str] = None,
        is_public: Optional[bool] = None
    ) -> int:
        """统计资源总数"""
        try:
            query = {}
            if assistant_id:
                query["assistant_id"] = assistant_id
            if status:
                query["status"] = status
            if is_public is not None:
                query["is_public"] = is_public
            return self.collection.count_documents(query)
        except Exception as e:
            from utils.logger import logger
            logger.error(f"统计资源总数失败: {str(e)}", exc_info=True)
            raise
    
    def update_resource_description(self, resource_id: str, description: str):
        """更新资源描述"""
        from bson import ObjectId
        try:
            if isinstance(resource_id, str):
                resource_id = ObjectId(resource_id)
            
            self.collection.update_one(
                {"_id": resource_id},
                {"$set": {"description": description, "updated_at": beijing_now()}}
            )
        except Exception as e:
            from utils.logger import logger
            logger.error(f"更新资源描述失败 - 资源ID: {resource_id}, 错误: {e}")
            raise
    
    def migrate_all_resources(self) -> Dict[str, Any]:
        """
        批量迁移所有旧版本资源到新版本
        
        Returns:
            迁移统计信息
        """
        from utils.logger import logger
        
        try:
            # 查找所有需要迁移的资源（版本小于2或没有版本字段）
            query = {
                "$or": [
                    {"schema_version": {"$exists": False}},
                    {"schema_version": {"$lt": 2}}
                ]
            }
            
            resources = list(self.collection.find(query))
            total_count = len(resources)
            
            logger.info(f"找到 {total_count} 个需要迁移的资源")
            
            migrated_count = 0
            failed_count = 0
            
            for resource in resources:
                try:
                    resource_id = resource["_id"]
                    migrated_resource = self._migrate_from_v1_to_v2(resource)
                    
                    # 更新数据库
                    update_fields = {
                        "schema_version": 2,
                        "updated_at": beijing_now()
                    }
                    
                    # 添加缺失的字段
                    if "status" not in migrated_resource:
                        update_fields["status"] = "active"
                    if "is_public" not in migrated_resource:
                        update_fields["is_public"] = True
                    if "tags" not in migrated_resource or migrated_resource["tags"] is None:
                        update_fields["tags"] = []
                    if "uploader_id" not in migrated_resource:
                        update_fields["uploader_id"] = None
                    if "thumbnail_url" not in migrated_resource:
                        update_fields["thumbnail_url"] = None
                    
                    self.collection.update_one(
                        {"_id": resource_id},
                        {"$set": update_fields}
                    )
                    
                    migrated_count += 1
                    
                except Exception as e:
                    logger.error(f"迁移资源失败: {str(resource.get('_id', 'Unknown'))}, 错误: {str(e)}")
                    failed_count += 1
            
            logger.info(f"资源迁移完成 - 总数: {total_count}, 成功: {migrated_count}, 失败: {failed_count}")
            
            return {
                "total": total_count,
                "migrated": migrated_count,
                "failed": failed_count
            }
            
        except Exception as e:
            logger.error(f"批量迁移资源失败: {str(e)}", exc_info=True)
            raise
    
    def update_resource_title(self, resource_id: str, title: str):
        """更新资源标题"""
        from bson import ObjectId
        try:
            if isinstance(resource_id, str):
                resource_id = ObjectId(resource_id)
            
            self.collection.update_one(
                {"_id": resource_id},
                {"$set": {"title": title, "updated_at": beijing_now()}}
            )
        except Exception as e:
            from utils.logger import logger
            logger.error(f"更新资源标题失败 - 资源ID: {resource_id}, 错误: {e}")
            raise
    
    def delete_resource(self, resource_id: str) -> bool:
        """
        删除资源
        
        Args:
            resource_id: 资源ID
        
        Returns:
            bool: 如果成功删除返回True，否则返回False
        """
        from bson import ObjectId
        try:
            if isinstance(resource_id, str):
                resource_id = ObjectId(resource_id)
            
            result = self.collection.delete_one({"_id": resource_id})
            return result.deleted_count > 0
        except Exception as e:
            from utils.logger import logger
            logger.error(f"删除资源失败 - 资源ID: {resource_id}, 错误: {e}")
            return False


class ResourceLikeRepository:
    """资源点赞仓库"""
    
    def __init__(self, mongodb_client: MongoDBClient):
        from utils.logger import logger
        logger.debug("初始化 ResourceLikeRepository...")
        self.collection = mongodb_client.get_collection("resource_likes")
        logger.debug(f"ResourceLikeRepository 初始化完成 - 集合: {self.collection.name}")
    
    def like_resource(self, user_id: str, resource_id: str) -> bool:
        """
        点赞资源
        
        Returns:
            True: 已点赞, False: 已取消点赞
        """
        existing = self.collection.find_one({
            "user_id": user_id,
            "resource_id": resource_id
        })
        
        if existing:
            # 取消点赞
            self.collection.delete_one({
                "user_id": user_id,
                "resource_id": resource_id
            })
            return False
        else:
            # 点赞
            self.collection.insert_one({
                "user_id": user_id,
                "resource_id": resource_id,
                "created_at": beijing_now()
            })
            return True
    
    def is_liked(self, user_id: str, resource_id: str) -> bool:
        """检查用户是否已点赞资源"""
        return self.collection.find_one({
            "user_id": user_id,
            "resource_id": resource_id
        }) is not None
    
    def count_likes(self, resource_id: str) -> int:
        """获取资源的点赞数"""
        return self.collection.count_documents({"resource_id": resource_id})
    
    def get_user_liked_resources(self, user_id: str) -> List[str]:
        """获取用户点赞的资源ID列表"""
        likes = self.collection.find({"user_id": user_id})
        return [like["resource_id"] for like in likes]


class ResourceFavoriteRepository:
    """资源收藏仓库"""
    
    def __init__(self, mongodb_client: MongoDBClient):
        from utils.logger import logger
        logger.debug("初始化 ResourceFavoriteRepository...")
        self.collection = mongodb_client.get_collection("resource_favorites")
        logger.debug(f"ResourceFavoriteRepository 初始化完成 - 集合: {self.collection.name}")
    
    def favorite_resource(self, user_id: str, resource_id: str) -> bool:
        """
        收藏资源
        
        Returns:
            True: 已收藏, False: 已取消收藏
        """
        existing = self.collection.find_one({
            "user_id": user_id,
            "resource_id": resource_id
        })
        
        if existing:
            # 取消收藏
            self.collection.delete_one({
                "user_id": user_id,
                "resource_id": resource_id
            })
            return False
        else:
            # 收藏
            self.collection.insert_one({
                "user_id": user_id,
                "resource_id": resource_id,
                "created_at": beijing_now()
            })
            return True
    
    def is_favorited(self, user_id: str, resource_id: str) -> bool:
        """检查用户是否已收藏资源"""
        return self.collection.find_one({
            "user_id": user_id,
            "resource_id": resource_id
        }) is not None
    
    def get_user_favorite_resources(self, user_id: str, skip: int = 0, limit: int = 100) -> List[str]:
        """获取用户收藏的资源ID列表"""
        favorites = self.collection.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(limit)
        return [fav["resource_id"] for fav in favorites]
    
    def count_favorites(self, resource_id: str) -> int:
        """获取资源的收藏数"""
        return self.collection.count_documents({"resource_id": resource_id})


# 全局MongoDB客户端实例（同步版本，用于文档处理）
mongodb_client = MongoDBClient()


