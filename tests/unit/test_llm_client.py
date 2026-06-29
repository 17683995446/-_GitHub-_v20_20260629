"""LLM 客户端单元测试（使用 mock，不依赖真实 API）。"""

from __future__ import annotations

from typing import Any

import pytest
import respx

from services.generator.llm_client import LLMClient, LLMResponse
from shared.config import get_settings


@pytest.fixture
def mock_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """注入测试配置。"""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("LLM_API_KEY", "sk_test_key")
    monkeypatch.setenv("LLM_API_BASE", "https://api.test.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_settings.cache_clear()


@pytest.fixture
def mock_llm_response() -> dict[str, Any]:
    """模拟 LLM API 响应。"""
    return {
        "id": "chatcmpl-test",
        "model": "test-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "这是一篇测试文章内容。",
                },
                "finish_reason": "stop",
                "index": 0,
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        },
    }


class TestLLMClient:
    """LLM 客户端测试。"""

    @respx.mock
    async def test_chat_success(
        self, mock_settings: None, mock_llm_response: dict[str, Any]
    ) -> None:
        """正常调用应返回 LLMResponse。"""
        respx.post("https://api.test.com/v1/chat/completions").respond(
            status_code=200, json=mock_llm_response
        )

        client = LLMClient()
        try:
            response = await client.chat(messages=[{"role": "user", "content": "test"}])
            assert isinstance(response, LLMResponse)
            assert response.content == "这是一篇测试文章内容。"
            assert response.model == "test-model"
            assert response.prompt_tokens == 100
            assert response.completion_tokens == 50
            assert response.total_tokens == 150
        finally:
            await client.close()

    @respx.mock
    async def test_chat_rate_limit(self, mock_settings: None) -> None:
        """限流应抛出 ExternalError。"""
        respx.post("https://api.test.com/v1/chat/completions").respond(
            status_code=429, json={"error": "rate limit"}
        )

        client = LLMClient()
        try:
            with pytest.raises(Exception, match="限流"):
                await client.chat(messages=[{"role": "user", "content": "test"}])
        finally:
            await client.close()

    @respx.mock
    async def test_chat_auth_error(self, mock_settings: None) -> None:
        """401 应抛出 GeneratorError。"""
        respx.post("https://api.test.com/v1/chat/completions").respond(
            status_code=401, json={"error": "invalid key"}
        )

        client = LLMClient()
        try:
            with pytest.raises(Exception, match="无效"):
                await client.chat(messages=[{"role": "user", "content": "test"}])
        finally:
            await client.close()

    async def test_missing_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """缺少 API Key 应报错。"""
        monkeypatch.setenv("LLM_API_KEY", "")
        get_settings.cache_clear()
        with pytest.raises(Exception, match="未配置"):
            LLMClient()
        get_settings.cache_clear()
