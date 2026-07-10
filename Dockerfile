# context-engine - 上下文感知 AI 工程基础设施 Dockerfile
# 基于稳定版本优化，保留缓存策略，使用国内镜像源加速
#
# 构建: DOCKER_BUILDKIT=1 docker build -t context-engine .
# 运行: docker run -p 8000:8000 --env-file .env.production context-engine
#
# 镜像源说明：
# - APT: 使用清华镜像 (mirrors.tuna.tsinghua.edu.cn)
# - pip: 使用清华镜像 (pypi.tuna.tsinghua.edu.cn)

# syntax=docker/dockerfile:1.4
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    UVICORN_PORT=8000 \
    UVICORN_WORKERS=24 \
    LIBREOFFICE_PATH=/usr/lib/libreoffice/program/soffice

WORKDIR /app

# 配置国内镜像源（加速下载）
# 配置 Debian APT 镜像源（使用清华镜像）
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources && \
        sed -i 's|https://security.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
        sed -i 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list && \
        sed -i 's|https://security.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list; \
    fi || true

# 配置 pip 镜像源（使用清华镜像）
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# 安装系统依赖（使用缓存加速，合并安装减少层数）
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends --fix-missing \
        git \
        libjpeg-dev \
        zlib1g-dev \
        libreoffice \
        libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

# 复制本地GitHub依赖（构建前需运行download_dependencies.sh/.ps1下载）
# 先复制vendor目录，这样如果本地有依赖就可以直接使用
# 注意：如果vendor目录不存在或为空，构建会失败，请先运行下载脚本
COPY vendor/ ./vendor/

# 安装 Python 依赖（requirements.txt 变化时重新构建）
# 注意：requirements.txt中已移除GitHub链接，改为从本地vendor目录安装
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ -d "./vendor/PaddleOCR" ] && [ "$(ls -A ./vendor/PaddleOCR)" ]; then \
        echo "从本地vendor目录安装PaddleOCR..."; \
        pip install -e ./vendor/PaddleOCR; \
    else \
        echo "错误: vendor/PaddleOCR 不存在或为空！"; \
        echo "请先运行 download_dependencies.sh (Linux/macOS) 或 download_dependencies.ps1 (Windows) 下载依赖"; \
        exit 1; \
    fi && \
    pip install -r requirements.txt

# 复制应用代码
COPY agents/ ./agents/
COPY chunking/ ./chunking/
COPY database/ ./database/
COPY embedding/ ./embedding/
COPY middleware/ ./middleware/
COPY models/ ./models/
COPY parsers/ ./parsers/
COPY retrieval/ ./retrieval/
COPY routers/ ./routers/
COPY services/ ./services/
COPY utils/ ./utils/
COPY main.py .env.production* ./

# 创建运行时目录
RUN mkdir -p /app/uploads /app/conversation_uploads /app/resources \
    /app/avatars /app/thumbnails /app/logs && \
    chmod -R 755 /app/uploads /app/conversation_uploads /app/resources \
    /app/avatars /app/thumbnails /app/logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${UVICORN_PORT:-8000} --workers ${UVICORN_WORKERS:-24}"]
