"""Prometheus 指标中间件。

提供 HTTP 请求计数、延迟直方图和管线运行指标。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# ===== HTTP 指标 =====
HTTP_REQUEST_COUNT = Counter(
    "gitcast_http_requests_total",
    "HTTP 请求总数",
    ["method", "endpoint", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "gitcast_http_request_duration_seconds",
    "HTTP 请求耗时（秒）",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

HTTP_IN_PROGRESS = Gauge(
    "gitcast_http_requests_in_progress",
    "当前处理中的请求数",
)

# ===== 管线指标 =====
PIPELINE_TOTAL = Counter(
    "gitcast_pipeline_total",
    "管线运行总数",
    ["status"],
)

PIPELINE_DURATION = Histogram(
    "gitcast_pipeline_duration_seconds",
    "管线运行耗时（秒）",
    buckets=(10, 30, 60, 120, 300, 600, 1800),
)

PIPELINE_PROJECTS_TOTAL = Counter(
    "gitcast_pipeline_projects_total",
    "管线处理的项目总数",
    ["status"],  # success / failed / skipped
)

# ===== 业务指标 =====
ARTICLES_GENERATED = Counter(
    "gitcast_articles_generated_total",
    "已生成文章总数",
)

AUDIO_SYNTHESIZED = Counter(
    "gitcast_audio_synthesized_total",
    "已合成音频总数",
    ["engine"],
)

PUBLISH_OPERATIONS = Counter(
    "gitcast_publish_operations_total",
    "发布操作总数",
    ["platform", "status"],
)

LLM_API_CALLS = Counter(
    "gitcast_llm_api_calls_total",
    "LLM API 调用总数",
    ["model", "status"],
)

LLM_TOKEN_USAGE = Counter(
    "gitcast_llm_token_usage_total",
    "LLM Token 使用量",
    ["type"],  # prompt / completion
)


def get_metrics_app() -> ASGIApp:
    """获取 Prometheus metrics ASGI 应用。"""
    metrics_app: ASGIApp = make_asgi_app()
    return metrics_app


async def metrics_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """FastAPI 中间件：记录 HTTP 指标。

    用法：
        app.middleware("http")(metrics_middleware)
    """
    import time

    method = request.method
    endpoint = request.url.path

    HTTP_IN_PROGRESS.inc()
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        HTTP_REQUEST_COUNT.labels(
            method=method,
            endpoint=endpoint,
            status="500",
        ).inc()
        raise
    finally:
        HTTP_IN_PROGRESS.dec()

    duration = time.perf_counter() - start_time
    HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
    HTTP_REQUEST_COUNT.labels(
        method=method,
        endpoint=endpoint,
        status=str(response.status_code),
    ).inc()

    return response
