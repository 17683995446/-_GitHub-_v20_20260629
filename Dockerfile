# GitCast Dockerfile — 多阶段构建
# 遵循最佳实践：小镜像、非root用户、分层缓存

# ===== 阶段1: 依赖安装 =====
FROM python:3.10-slim AS builder

# 系统依赖（编译 asyncpg/lxml/bcrypt 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# 先复制依赖文件，利用 Docker 层缓存
COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install \
    fastapi uvicorn[standard] pydantic pydantic-settings \
    sqlalchemy asyncpg structlog httpx tenacity \
    beautifulsoup4 lxml pyyaml \
    pyjwt "passlib[bcrypt]" email-validator \
    redis hiredis \
    pytest pytest-asyncio respx ruff mypy

# ===== 阶段2: 运行时镜像 =====
FROM python:3.10-slim AS runtime

# 运行时系统依赖（仅 libpq 和 libxml2）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libxml2 libxslt1.1 nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制已安装的 Python 包
COPY --from=builder /install /usr/local

# 创建非 root 用户
RUN groupadd -r gitcast && useradd -r -g gitcast -s /bin/bash gitcast

WORKDIR /app

# 复制项目代码
COPY --chown=gitcast:gitcast . /app/

# 创建存储目录
RUN mkdir -p /app/storage /app/logs && chown -R gitcast:gitcast /app

# 切换到非 root 用户
USER gitcast

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import httpx; r=httpx.get('http://localhost:8000/api/v1/health'); exit(0 if r.status_code==200 else 1)"

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
