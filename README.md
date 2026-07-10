# context-engine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/release-1.0.0-228b22.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-009688.svg)](https://fastapi.tiangolo.com/)

`context-engine` 是一个用于构建检索、记忆与上下文感知 AI 系统的工程基础设施。后端基于 FastAPI，提供文档入库、混合检索、证据上下文组装、流式聊天、深度研究和运行时配置接口；前端以后续主维护的 `web-tanstack/` 为主，旧 `web/` Next.js 版本仅作为历史兼容和功能平移参照保留。

当前发布版本为 `1.0.0`。后端版本号的单一来源是 [utils/version.py](utils/version.py)，健康检查和 OpenAPI 版本都会读取它。

## 功能范围

- 通用对话：匿名访问，支持会话列表、会话详情、消息追加、重命名、删除和重新生成。
- 上下文增强问答：聊天请求可选择知识空间，并通过向量库、关键词和图谱关联做检索增强。
- 文档入库：支持 PDF、Word、Markdown、TXT 等常见文档上传、解析、分块、嵌入、入库和进度查询。
- 知识空间：提供知识空间列表和创建接口，用于组织文档与检索范围。
- 深度研究：针对复杂问题提供多 Agent 协作式分析，并提供进入深度研究前的轻量评估接口。
- 运行时设置：支持模型、Agent 和请求日志等运行时配置，部分配置可通过 API 动态调整。
- 健康检查：暴露 liveness、readiness、依赖状态和基础系统指标。

已从当前主线中移除或不作为核心维护范围的能力包括：登录认证、用户系统、通知、邮件、后台管理、资源社区和 Comsol/mph-agent 等非上下文核心功能。

## 技术栈

后端：

- FastAPI + Uvicorn
- MongoDB：会话、文档元数据、配置等业务数据
- Qdrant：向量检索
- Neo4j：知识图谱与关联检索
- Redis：缓存能力
- Ollama：本地大模型与嵌入模型调用
- LangChain、jieba、sentence-transformers：文本处理、分块与重排
- PyPDF2、PyMuPDF、python-docx、Unstructured、PaddleOCR：文档解析与 OCR

前端：

- [web-tanstack/](web-tanstack)：主前端，Vite、React 19、TanStack Router、TanStack Query、TanStack Table、Zustand、Tailwind CSS
- [web/](web)：旧 Next.js 16 前端，仅作为历史兼容和迁移参考

## 目录结构

```txt
context-engine/
├── agents/              # 通用对话、深度研究与专家 Agent
├── chunking/            # 文本分块与分块路由
├── database/            # MongoDB、Qdrant 等连接与仓储
├── docs/                # 补充文档
├── embedding/           # 嵌入服务
├── eval/                # 评测相关代码
├── middleware/          # FastAPI 中间件
├── models/              # 数据模型
├── parsers/             # 文档解析器
├── retrieval/           # 查询分析、检索与重排
├── routers/             # FastAPI API 路由
├── scripts/             # 运维、验证、迁移脚本
├── services/            # 业务服务层
├── tests/               # 测试
├── utils/               # 日志、监控、版本、通用工具
├── web/                 # 旧 Next.js 前端（历史兼容）
└── web-tanstack/        # 主前端，Vite + TanStack
```

## 快速开始

### 1. 准备基础环境

建议环境：

- Python 3.10+
- Node.js 20+
- Docker / Docker Compose
- Ollama，本地模型服务可选，但聊天、嵌入和 RAG 相关能力依赖它

如果使用本仓库的 `docker-compose.yml` 启动本地依赖，默认端口如下：

| 服务 | 地址 |
| --- | --- |
| MongoDB | `localhost:27017` |
| Qdrant REST | `localhost:6333` |
| Qdrant gRPC | `localhost:6334` |
| Neo4j HTTP | `localhost:7474` |
| Neo4j Bolt | `localhost:7687` |
| Redis | `localhost:6379` |

### 2. 启动本地依赖

```bash
docker compose up -d
```

这个 compose 文件只启动 MongoDB、Qdrant、Neo4j 和 Redis，不启动 FastAPI 应用本身。

文档入库处理默认会优先投递到 Celery/Redis 队列。Windows 本地开发可以在另一个 PowerShell 里启动 worker：

```powershell
.\scripts\start-celery-worker.ps1
```

如果暂时不启动 worker，可在环境变量里设置 `DOCUMENT_TASK_BACKEND=local`。不建议在常规开发中静默回退到进程内任务；确实需要兼容旧行为时，再显式设置 `DOCUMENT_TASK_FALLBACK_LOCAL=true` 让上传在 Celery 投递失败时回退到 FastAPI BackgroundTasks。

### 3. 准备 Python 依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果需要 PaddleOCR，先下载 vendor 依赖，再安装本地包：

```bash
chmod +x download_dependencies.sh
./download_dependencies.sh
pip install -e ./vendor/PaddleOCR
```

Windows 可以使用：

```powershell
.\download_dependencies.ps1
```

### 4. 配置环境变量

开发环境默认会优先加载 `.env.development`；生产环境会优先加载 `.env.production`。如果这些文件不存在，会回退到 `.env`。

本地开发可直接参考 [.env.development](.env.development)。关键配置如下：

```env
ENVIRONMENT=development
SECRET_KEY=dev-secret-key-change-me
API_HOST=0.0.0.0
API_PORT=8000

MONGODB_URI=mongodb://admin:admin123@localhost:27017/advanced_rag?authSource=admin
MONGODB_DB_NAME=advanced_rag

QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:1b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

MAX_UPLOAD_SIZE=104857600
UPLOAD_DIR=./uploads

LOG_LEVEL=INFO
LOG_FILE=./logs/context-engine-api.log
```

如果后端运行在容器里，而 MongoDB、Qdrant、Neo4j、Redis 或 Ollama 运行在宿主机，参考 [.env.docker.local](.env.docker.local)，把地址改成 `host.docker.internal`。

### 5. 准备 Ollama 模型

按环境变量中的模型名拉取模型：

```bash
ollama pull gemma3:1b
ollama pull nomic-embed-text
```

也可以在 `.env.development` 中替换为你本地已有的模型。若 Ollama 未启动，FastAPI 进程仍可启动，但模型调用、嵌入和 RAG 入库能力会失败或降级。

### 6. 启动后端

```bash
python main.py
```

或者：

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

启动后访问：

- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`
- 存活探针：`http://localhost:8000/health/liveness`
- 就绪探针：`http://localhost:8000/health/readiness`
- 指标：`http://localhost:8000/health/metrics`

### 7. 启动前端

主前端（TanStack）：

```bash
cd web-tanstack
npm install
npm run generate:api
npm run dev
```

默认访问 `http://localhost:5173`。如需指定后端地址，在 `web-tanstack/.env.local` 中配置：

```env
VITE_API_URL=http://localhost:8000
```

历史 Next.js 前端（仅兼容/迁移参考）：

```bash
cd web
npm install
npm run dev
```

默认访问 `http://localhost:3000`。如需指定后端地址，在 `web/.env.local` 中配置：

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Docker 构建 API 镜像

构建镜像前需要确保 `vendor/PaddleOCR` 已存在：

```bash
./download_dependencies.sh
DOCKER_BUILDKIT=1 docker build -t context-engine .
```

运行 API 容器：

```bash
docker run -d \
  --name context-engine-api \
  -p 8000:8000 \
  --env-file .env.docker.local \
  context-engine
```

`docker-compose.yml` 当前用于本地依赖服务。如果需要把 API 也纳入 compose，需要额外添加应用服务并处理模型、上传目录、日志目录和依赖健康检查。

## 主要 API

聊天与会话：

- `GET /api/chat/models`：获取 Ollama 可用模型
- `POST /api/chat`：常规聊天 / 上下文增强聊天，返回 SSE 流
- `POST /api/chat/deep-research`：深度研究模式
- `POST /api/chat/deep-research/evaluate`：评估问题是否值得进入深度研究
- `GET /api/chat/conversations`：会话列表
- `POST /api/chat/conversations`：创建会话
- `GET /api/chat/conversations/{conversation_id}`：会话详情
- `POST /api/chat/conversations/{conversation_id}/messages`：追加消息
- `PUT /api/chat/conversations/{conversation_id}`：更新会话
- `DELETE /api/chat/conversations/{conversation_id}`：删除会话
- `PUT /api/chat/conversations/{conversation_id}/messages/{message_id}`：更新消息
- `POST /api/chat/conversations/{conversation_id}/messages/{message_id}/regenerate`：重新生成消息
- `POST /api/chat/conversation-attachment`：上传对话附件并入库，成功返回 `202 Accepted` 和后台任务信息
- `GET /api/chat/conversation-attachment/{conversation_id}/{file_id}/status`：查询附件处理状态

文档与知识空间：

- `GET /api/knowledge-spaces`：知识空间列表
- `POST /api/knowledge-spaces`：创建知识空间
- `POST /api/documents/upload`：上传文档
- `GET /api/documents`：文档列表
- `GET /api/documents/{doc_id}`：文档详情
- `PUT /api/documents/{doc_id}`：更新文档
- `DELETE /api/documents/{doc_id}`：删除文档
- `GET /api/documents/{doc_id}/progress`：文档处理进度
- `GET /api/documents/{doc_id}/progress/stream`：文档处理进度 SSE 流
- `POST /api/documents/{doc_id}/retry`：重试文档处理
- `GET /api/documents/{doc_id}/preview`：文档预览

检索、助手与设置：

- `POST /api/retrieval/analyze`：查询分析
- `POST /api/retrieval`：检索
- `GET /api/assistants`：助手列表
- `GET /api/assistants/{assistant_id}`：助手详情
- `GET /api/settings/runtime`：读取运行时配置
- `PUT /api/settings/runtime`：更新运行时配置
- `GET /api/settings/agents`：读取 Agent 配置
- `PUT /api/settings/agents/{agent_type}`：更新指定 Agent 配置

## 日志配置

基础日志配置来自环境变量：

```env
LOG_LEVEL=INFO
LOG_FILE=./logs/context-engine-api.log
```

HTTP 请求日志可以通过运行时配置动态调整：

```http
PUT /api/settings/runtime
```

示例请求体：

```json
{
  "params": {
    "http_log_level": "INFO",
    "http_log_request_level": "DEBUG",
    "http_log_success_enabled": true,
    "http_log_success_level": "INFO",
    "http_log_slow_threshold_s": 0.8,
    "http_log_slow_level": "WARNING",
    "http_log_client_error_level": "WARNING",
    "http_log_server_error_level": "ERROR",
    "http_log_include_query": true,
    "http_log_include_client_ip": true,
    "http_log_include_request_body": false,
    "http_log_request_body_max_chars": 1200,
    "http_log_exclude_prefixes": ["/health", "/api/health"]
  }
}
```

完整说明见 [docs/logging-settings.md](docs/logging-settings.md)。

## 开发命令

后端：

```bash
python main.py
pytest
```

TanStack 主前端：

```bash
cd web-tanstack
npm run generate:api
npm run verify
```

历史 Next.js 前端（可选兼容检查）：

```bash
cd web
npm run lint
npm run build
```

本地依赖：

```bash
docker compose ps
docker compose logs -f mongodb
docker compose logs -f qdrant
docker compose logs -f neo4j
docker compose logs -f redis
```

## 验证与排查

先确认 API 进程是否存活：

```bash
curl http://localhost:8000/health/liveness
```

再确认依赖连接状态：

```bash
curl http://localhost:8000/health
```

如果 MongoDB 显示 unhealthy，检查：

- `docker compose ps mongodb`
- `.env.development` 中的 `MONGODB_URI`
- 是否使用了 compose 默认账号：`admin/admin123`
- 是否带上 `authSource=admin`

如果 Qdrant 显示 unhealthy，检查：

- `curl http://localhost:6333/healthz`
- `.env.development` 中的 `QDRANT_URL`

如果聊天或入库失败，优先检查：

- `ollama list`
- `ollama ps`
- `.env.development` 中的 `OLLAMA_BASE_URL`
- `OLLAMA_MODEL` 和 `OLLAMA_EMBEDDING_MODEL` 是否已经拉取

## 相关文档

- [CHANGELOG.md](CHANGELOG.md)：版本变更
- [CONTRIBUTING.md](CONTRIBUTING.md)：贡献说明
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)：行为准则
- [chunking/README.md](chunking/README.md)：分块模块说明
- [parsers/README.md](parsers/README.md)：解析模块说明
- [utils/README.md](utils/README.md)：工具模块说明
- [scripts/README_MIGRATIONS.md](scripts/README_MIGRATIONS.md)：迁移脚本说明
- [vendor/README.md](vendor/README.md)：本地第三方依赖说明
- [web-tanstack/README.md](web-tanstack/README.md)：TanStack 主前端说明
- [web/README.md](web/README.md)：旧 Next.js 前端兼容说明

## License

本项目使用 [MIT License](LICENSE)。
