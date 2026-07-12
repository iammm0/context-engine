# context-engine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/release-1.0.0-228b22.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-009688.svg)](https://fastapi.tiangolo.com/)

`context-engine` is engineering infrastructure for building retrieval, memory, and context-aware AI systems. The backend is built with FastAPI and provides document ingestion, hybrid retrieval, evidence-context assembly, streaming chat, deep research, and runtime configuration APIs. The actively maintained frontend is `web-tanstack/`; the legacy `web/` Next.js app is kept only for historical compatibility and feature-migration reference.

The current release is `1.0.0`. The single source of truth for the backend version is [utils/version.py](utils/version.py), which is also used by health checks and OpenAPI metadata.

## Feature Scope

- General chat: anonymous access, conversation lists, conversation details, message append, rename, delete, and regeneration.
- Context-augmented Q&A: chat requests can select knowledge spaces and enhance retrieval through vector search, keyword search, and graph associations.
- Document ingestion: supports uploads for common document formats such as PDF, Word, Markdown, and TXT, then parses, chunks, embeds, stores, and tracks processing progress.
- Knowledge spaces: provides APIs for listing and creating knowledge spaces so documents and retrieval scope can be organized.
- Deep research: provides multi-agent collaborative analysis for complex questions, plus a lightweight evaluation endpoint before entering deep research.
- Runtime settings: supports dynamic runtime configuration for models, agents, and request logging.
- Health checks: exposes liveness, readiness, dependency status, and basic system metrics.

Capabilities removed from the current mainline or no longer treated as core maintenance scope include login/authentication, user systems, notifications, email, admin management, resource community features, and non-context-core features such as Comsol/mph-agent.

## Tech Stack

Backend:

- FastAPI + Uvicorn
- MongoDB for conversations, document metadata, configuration, and other application data
- Qdrant for vector retrieval
- Neo4j for knowledge graphs and graph-assisted retrieval
- Redis for caching and task queue infrastructure
- Ollama for local LLM and embedding model calls
- LangChain, jieba, and sentence-transformers for text processing, chunking, and reranking
- PyPDF2, PyMuPDF, python-docx, unstructured, and PaddleOCR for document parsing and OCR

Frontend:

- [web-tanstack/](web-tanstack): the primary frontend, built with Vite, React 19, TanStack Router, TanStack Query, TanStack Table, Zustand, and Tailwind CSS
- [web/](web): the legacy Next.js 16 frontend, kept only for compatibility and migration reference

## Repository Layout

```txt
context-engine/
|-- agents/              # General chat, deep research, and expert agents
|-- chunking/            # Text chunking and chunking routers
|-- database/            # MongoDB, Qdrant, and related storage clients
|-- docs/                # Supplemental documentation
|-- embedding/           # Embedding services
|-- eval/                # Evaluation-related code
|-- middleware/          # FastAPI middleware
|-- models/              # Data models
|-- parsers/             # Document parsers
|-- retrieval/           # Query analysis, retrieval, and reranking
|-- routers/             # FastAPI API routers
|-- scripts/             # Operations, verification, and migration scripts
|-- services/            # Business service layer
|-- tests/               # Tests
|-- utils/               # Logging, monitoring, versioning, and shared utilities
|-- web/                 # Legacy Next.js frontend
`-- web-tanstack/        # Primary Vite + TanStack frontend
```

## Quick Start

### 1. Prepare the Base Environment

Recommended environment:

- Python 3.10+
- Node.js 20+
- Docker / Docker Compose
- Ollama. The local model service is optional for process startup, but chat, embedding, and RAG ingestion capabilities depend on it.

When using this repository's `docker-compose.yml` to start local dependencies, the default ports are:

| Service | Address |
| --- | --- |
| MongoDB | `localhost:27017` |
| Qdrant REST | `localhost:6333` |
| Qdrant gRPC | `localhost:6334` |
| Neo4j HTTP | `localhost:7474` |
| Neo4j Bolt | `localhost:7687` |
| Redis | `localhost:6379` |

### 2. Start Local Dependencies

```bash
docker compose up -d
```

This compose file starts only MongoDB, Qdrant, Neo4j, and Redis. It does not start the FastAPI application itself.

Document ingestion is submitted to the Celery/Redis queue by default. For local development on Windows, start a worker in another PowerShell session:

```powershell
.\scripts\start-celery-worker.ps1
```

If you temporarily do not want to start a worker, set `DOCUMENT_TASK_BACKEND=local`. Routine development should avoid silently falling back to in-process tasks. If legacy behavior is explicitly needed, set `DOCUMENT_TASK_FALLBACK_LOCAL=true` so uploads fall back to FastAPI `BackgroundTasks` when Celery submission fails.

### 3. Install Python Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If PaddleOCR is needed, download vendor dependencies first and then install the local package:

```bash
chmod +x download_dependencies.sh
./download_dependencies.sh
pip install -e ./vendor/PaddleOCR
```

On Windows, use:

```powershell
.\download_dependencies.ps1
```

### 4. Configure Environment Variables

The development environment loads `.env.development` first. The production environment loads `.env.production` first. If those files do not exist, the application falls back to `.env`.

For local development, you can use [.env.development](.env.development) as a reference. Key settings:

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

If the backend runs in a container while MongoDB, Qdrant, Neo4j, Redis, or Ollama run on the host machine, use [.env.docker.local](.env.docker.local) as a reference and change host addresses to `host.docker.internal`.

### 5. Prepare Ollama Models

Pull the models named in the environment variables:

```bash
ollama pull gemma3:1b
ollama pull nomic-embed-text
```

You can also replace them in `.env.development` with models that already exist locally. If Ollama is not running, the FastAPI process can still start, but model calls, embedding, and RAG ingestion will fail or degrade.

### 6. Start the Backend

```bash
python main.py
```

Or:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

After startup, visit:

- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`
- Liveness probe: `http://localhost:8000/health/liveness`
- Readiness probe: `http://localhost:8000/health/readiness`
- Metrics: `http://localhost:8000/health/metrics`

### 7. Start the Frontend

Primary TanStack frontend:

```bash
cd web-tanstack
npm install
npm run generate:api
npm run dev
```

The default URL is `http://localhost:5173`. To specify the backend address, configure `web-tanstack/.env.local`:

```env
VITE_API_URL=http://localhost:8000
```

Legacy Next.js frontend, kept only for compatibility and migration reference:

```bash
cd web
npm install
npm run dev
```

The default URL is `http://localhost:3000`. To specify the backend address, configure `web/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Build the API Docker Image

Before building the image, make sure `vendor/PaddleOCR` exists:

```bash
./download_dependencies.sh
DOCKER_BUILDKIT=1 docker build -t context-engine .
```

Run the API container:

```bash
docker run -d \
  --name context-engine-api \
  -p 8000:8000 \
  --env-file .env.docker.local \
  context-engine
```

`docker-compose.yml` is currently used for local dependency services. If the API should also be managed by compose, add an application service and handle models, upload directories, log directories, and dependency health checks explicitly.

## Main APIs

Chat and conversations:

- `GET /api/chat/models`: list available Ollama models
- `POST /api/chat`: regular chat or context-augmented chat, returned as an SSE stream
- `POST /api/chat/deep-research`: deep research mode
- `POST /api/chat/deep-research/evaluate`: evaluate whether a question is worth deep research
- `GET /api/chat/conversations`: list conversations
- `POST /api/chat/conversations`: create a conversation
- `GET /api/chat/conversations/{conversation_id}`: get conversation details
- `POST /api/chat/conversations/{conversation_id}/messages`: append a message
- `PUT /api/chat/conversations/{conversation_id}`: update a conversation
- `DELETE /api/chat/conversations/{conversation_id}`: delete a conversation
- `PUT /api/chat/conversations/{conversation_id}/messages/{message_id}`: update a message
- `POST /api/chat/conversations/{conversation_id}/messages/{message_id}/regenerate`: regenerate a message
- `POST /api/chat/conversation-attachment`: upload a conversation attachment for ingestion; returns `202 Accepted` and background task information on success
- `GET /api/chat/conversation-attachment/{conversation_id}/{file_id}/status`: query attachment processing status

Documents and knowledge spaces:

- `GET /api/knowledge-spaces`: list knowledge spaces
- `POST /api/knowledge-spaces`: create a knowledge space
- `POST /api/documents/upload`: upload a document
- `GET /api/documents`: list documents
- `GET /api/documents/{doc_id}`: get document details
- `PUT /api/documents/{doc_id}`: update a document
- `DELETE /api/documents/{doc_id}`: delete a document
- `GET /api/documents/{doc_id}/progress`: get document processing progress
- `GET /api/documents/{doc_id}/progress/stream`: stream document processing progress through SSE
- `POST /api/documents/{doc_id}/retry`: retry document processing
- `GET /api/documents/{doc_id}/preview`: preview a document

Retrieval, assistants, and settings:

- `POST /api/retrieval/analyze`: analyze a query
- `POST /api/retrieval`: run retrieval
- `GET /api/assistants`: list assistants
- `GET /api/assistants/{assistant_id}`: get assistant details
- `GET /api/settings/runtime`: read runtime configuration
- `PUT /api/settings/runtime`: update runtime configuration
- `GET /api/settings/agents`: read agent configuration
- `PUT /api/settings/agents/{agent_type}`: update a specific agent configuration

## Logging Configuration

Basic logging configuration comes from environment variables:

```env
LOG_LEVEL=INFO
LOG_FILE=./logs/context-engine-api.log
```

HTTP request logging can be adjusted dynamically through runtime configuration:

```http
PUT /api/settings/runtime
```

Example request body:

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

See [docs/logging-settings.md](docs/logging-settings.md) for the full description.

## Development Commands

Backend:

```bash
python main.py
pytest
```

Primary TanStack frontend:

```bash
cd web-tanstack
npm run generate:api
npm run verify
```

Legacy Next.js frontend, optional compatibility check:

```bash
cd web
npm run lint
npm run build
```

Local dependencies:

```bash
docker compose ps
docker compose logs -f mongodb
docker compose logs -f qdrant
docker compose logs -f neo4j
docker compose logs -f redis
```

## Verification and Troubleshooting

First confirm that the API process is alive:

```bash
curl http://localhost:8000/health/liveness
```

Then confirm dependency connection status:

```bash
curl http://localhost:8000/health
```

If MongoDB is unhealthy, check:

- `docker compose ps mongodb`
- `MONGODB_URI` in `.env.development`
- Whether the compose default account is being used: `admin/admin123`
- Whether `authSource=admin` is included

If Qdrant is unhealthy, check:

- `curl http://localhost:6333/healthz`
- `QDRANT_URL` in `.env.development`

If chat or ingestion fails, check:

- `ollama list`
- `ollama ps`
- `OLLAMA_BASE_URL` in `.env.development`
- Whether `OLLAMA_MODEL` and `OLLAMA_EMBEDDING_MODEL` have already been pulled

## Related Documentation

- [CHANGELOG.md](CHANGELOG.md): version changes
- [CONTRIBUTING.md](CONTRIBUTING.md): contribution guide
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md): code of conduct
- [chunking/README.md](chunking/README.md): chunking module guide
- [parsers/README.md](parsers/README.md): parser module guide
- [utils/README.md](utils/README.md): utility module guide
- [scripts/README_MIGRATIONS.md](scripts/README_MIGRATIONS.md): migration script guide
- [vendor/README.md](vendor/README.md): local third-party dependency notes
- [web-tanstack/README.md](web-tanstack/README.md): primary TanStack frontend guide
- [web/README.md](web/README.md): legacy Next.js frontend compatibility guide

## License

This project is licensed under the [MIT License](LICENSE).
