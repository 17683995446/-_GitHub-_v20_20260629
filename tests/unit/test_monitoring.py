"""监控中间件单元测试。"""

from __future__ import annotations

import pytest

from api.middleware import (
    ARTICLES_GENERATED,
    AUDIO_SYNTHESIZED,
    HTTP_REQUEST_COUNT,
    HTTP_REQUEST_DURATION,
    PIPELINE_TOTAL,
    PUBLISH_OPERATIONS,
    get_metrics_app,
    metrics_middleware,
)


class TestPrometheusMetrics:
    """Prometheus 指标测试。"""

    def test_metrics_app_exists(self) -> None:
        """metrics ASGI 应用应可创建。"""
        app = get_metrics_app()
        assert app is not None

    def test_http_request_counter(self) -> None:
        """HTTP 请求计数器应可自增。"""
        HTTP_REQUEST_COUNT.labels(
            method="GET",
            endpoint="/health",
            status="200",
        ).inc()
        # 验证计数器存在于注册表中
        from prometheus_client import generate_latest

        output = generate_latest().decode("utf-8")
        assert "gitcast_http_requests_total" in output

    def test_pipeline_counter(self) -> None:
        """管线计数器应支持多种状态。"""
        for status in ["completed", "failed"]:
            PIPELINE_TOTAL.labels(status=status).inc()

    def test_article_counter(self) -> None:
        """文章生成计数器应可自增。"""
        ARTICLES_GENERATED.inc()

    def test_audio_counter_with_labels(self) -> None:
        """音频计数器应支持引擎标签。"""
        AUDIO_SYNTHESIZED.labels(engine="azure").inc()
        AUDIO_SYNTHESIZED.labels(engine="cosyvoice").inc()

    def test_publish_counter_with_labels(self) -> None:
        """发布计数器应支持平台和状态标签。"""
        PUBLISH_OPERATIONS.labels(platform="ximalaya", status="success").inc()
        PUBLISH_OPERATIONS.labels(platform="wechat", status="failed").inc()

    def test_http_duration_histogram(self) -> None:
        """HTTP 延迟直方图应可记录。"""
        HTTP_REQUEST_DURATION.labels(method="POST", endpoint="/pipeline/run").observe(0.5)


class TestMetricsMiddleware:
    """指标中间件测试。"""

    @pytest.mark.asyncio
    async def test_middleware_records_metrics(self) -> None:
        """中间件应记录请求指标。"""
        from unittest.mock import AsyncMock, MagicMock

        # 模拟请求和响应
        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_request.url.path = "/api/v1/health"

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_call_next = AsyncMock(return_value=mock_response)

        response = await metrics_middleware(mock_request, mock_call_next)

        assert response is mock_response
        mock_call_next.assert_called_once_with(mock_request)
