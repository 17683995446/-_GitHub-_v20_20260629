"""FastAPI 应用工厂。

遵循架构规范：应用入口点，只做路由注册和中间件配置。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.v1.auth import router as auth_router
from api.v1.content import router as content_router
from api.v1.health import router as health_router
from api.v1.pipeline import router as pipeline_router
from api.v1.quickgen import router as quickgen_router
from api.v1.stats import router as stats_router
from api.v1.tts import router as tts_router
from shared.config import get_settings
from shared.errors import GitCastError
from shared.logging import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期管理。"""
    settings = get_settings()
    setup_logging(settings.app_log_level)
    logger.info("app_starting", env=settings.app_env, port=settings.app_port)

    yield

    # 关闭资源
    from shared.database import close_engine

    await close_engine()
    logger.info("app_stopped")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    settings = get_settings()

    app = FastAPI(
        title="GitCast API",
        description="自动发现 GitHub 高价值项目，生成通俗解读音频文档",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Prometheus 指标中间件
    from api.middleware import get_metrics_app, metrics_middleware

    app.middleware("http")(metrics_middleware)

    # /metrics 端点（Prometheus 抓取）
    app.mount("/metrics", get_metrics_app())

    # 统一异常处理：GitCastError → JSON 响应
    @app.exception_handler(GitCastError)
    async def gitcast_error_handler(request: Request, exc: GitCastError) -> JSONResponse:
        """将自定义异常转换为 JSON 响应。"""
        # 认证错误返回 401，其他业务错误返回 400
        from shared.errors import AuthError

        status_code = 401 if isinstance(exc, AuthError) else 400
        logger.warning(
            "api_error",
            code=exc.code,
            message=exc.message,
            path=str(request.url.path),
        )
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    # 注册路由
    api_prefix = "/api/v1"
    app.include_router(health_router, prefix=api_prefix)
    app.include_router(quickgen_router, prefix=api_prefix)
    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(pipeline_router, prefix=api_prefix)
    app.include_router(content_router, prefix=api_prefix)
    app.include_router(stats_router, prefix=api_prefix)
    app.include_router(tts_router, prefix=api_prefix)

    # 静态文件服务（音频文件）
    from pathlib import Path

    storage_path = Path(settings.storage_local_path)
    storage_path.mkdir(parents=True, exist_ok=True)
    app.mount("/storage", StaticFiles(directory=str(storage_path)), name="storage")

    # 控制台静态页面
    console_path = Path("/workspace/gitcast-console")
    if console_path.exists():
        app.mount("/console", StaticFiles(directory=str(console_path), html=True), name="console")

    return app
