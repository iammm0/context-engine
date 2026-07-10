"""FastAPI应用入口"""
import warnings

# 抑制 jieba 库中 pkg_resources 的弃用警告
# 这是第三方库的问题，不影响功能，等待 jieba 更新即可
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*", category=UserWarning)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import os
from dotenv import load_dotenv
from routers import chat, documents, retrieval, assistants, health, knowledge_spaces, settings
from utils.logger import logger
from utils.lifespan import lifespan
from middleware.logging_middleware import log_requests

# 根据环境变量加载对应的配置文件
# 优先使用 ENVIRONMENT 环境变量，如果没有则根据 NODE_ENV 或默认使用 development
env_mode = os.getenv("ENVIRONMENT") or os.getenv("NODE_ENV", "development")
base_dir = os.path.dirname(__file__)

# 确定要加载的配置文件
if env_mode == "production":
    env_file = ".env.production"
else:
    env_file = ".env.development"

# 首先尝试加载环境特定的配置文件
env_path = os.path.join(base_dir, env_file)
loaded_file = None
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)
    loaded_file = env_path
else:
    # 如果环境特定文件不存在，尝试加载通用的 .env 文件
    default_env_path = os.path.join(base_dir, ".env")
    if os.path.exists(default_env_path):
        load_dotenv(default_env_path, override=True)
        loaded_file = default_env_path
    else:
        # 尝试从项目根目录加载
        root_env_path = os.path.join(os.path.dirname(base_dir), ".env")
        if os.path.exists(root_env_path):
            load_dotenv(root_env_path, override=True)
            loaded_file = root_env_path
        else:
            # 使用默认的 load_dotenv()，会在当前目录和父目录中查找
            load_dotenv()
            loaded_file = "默认环境变量（未找到配置文件）"


app = FastAPI(
    title="Context Engine API",
    description="上下文感知 AI 工程基础设施：AI 助手对话（含深度研究）与知识库检索/入库",
    version="v0.8.5",
    lifespan=lifespan
)

# CORS中间件配置 - 允许所有来源访问（调试模式）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# 请求日志中间件
app.middleware("http")(log_requests)

# 静态文件服务 - 头像文件
avatars_dir = os.path.join(base_dir, "avatars")
os.makedirs(avatars_dir, exist_ok=True)
app.mount("/avatars", StaticFiles(directory=avatars_dir), name="avatars")

# 静态文件服务 - 视频封面
thumbnails_dir = os.path.join(base_dir, "thumbnails")
os.makedirs(thumbnails_dir, exist_ok=True)
app.mount("/thumbnails", StaticFiles(directory=thumbnails_dir), name="thumbnails")

# 静态文件服务 - 资源封面
cover_images_dir = os.path.join(base_dir, "cover_images")
os.makedirs(cover_images_dir, exist_ok=True)
app.mount("/cover_images", StaticFiles(directory=cover_images_dir), name="cover_images")

# 注册路由
app.include_router(chat.router, prefix="/api/chat", tags=["聊天"])
# 文档管理路由
app.include_router(documents.router, prefix="/api/documents", tags=["文档管理"])
app.include_router(retrieval.router, prefix="/api/retrieval", tags=["检索服务"])
app.include_router(assistants.router, prefix="/api/assistants", tags=["助手"])
app.include_router(knowledge_spaces.router, prefix="/api/knowledge-spaces", tags=["知识空间"])
app.include_router(settings.router, prefix="/api/settings", tags=["设置"])
app.include_router(health.router, tags=["健康检查"])


@app.get("/")
async def root():
    """根路径"""
    return {"message": "context-engine API 服务", "version": "v0.8.5"}


# 健康检查端点已移至 routers/health.py


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    logger.error(
        f"未处理的异常: {str(exc)}",
        exc_info=True,
        extra={"path": str(request.url.path), "method": request.method}
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"内部服务器错误: {str(exc)}"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*"
        }
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    
    # 根据环境显示不同的服务地址
    is_production = env_mode == "production"
    
    host = os.getenv("HOST", "0.0.0.0")

    # 只显示环境信息和使用的环境变量文件
    env_name = "生产环境" if is_production else "开发环境"
    print(f"\n环境: {env_name}")
    print(f"环境变量文件: {loaded_file}\n")
    
    # Worker数量配置：生产环境使用多worker，开发环境单worker
    # 支持通过环境变量UVICORN_WORKERS覆盖
    if is_production:
        workers = int(os.getenv("UVICORN_WORKERS", "24"))  # 默认24个worker（48核的一半）
        print(f"Worker数量: {workers}")
    else:
        workers = 1  # 开发环境单worker，支持reload

    # 初始化启动日志：明确监听端口/地址
    try:
        logger.info(
            f"服务启动参数 - 环境: {env_name}, 监听: {host}:{port}, "
            f"workers: {workers if is_production else 1}, reload: {not is_production}, "
            f"env_file: {loaded_file}"
        )
    except Exception:
        # 避免日志系统异常影响启动
        pass
    
    # 生产环境不启用reload，开发环境启用
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        workers=workers if is_production else None,  # 生产环境使用多worker
        reload=not is_production,  # 生产环境禁用reload
        log_config=None,  # 使用自定义日志配置
        timeout_keep_alive=900,  # 增加keep-alive超时时间（15分钟），支持大文件上传
        limit_concurrency=2000,  # 每个worker的并发连接数限制
    )
