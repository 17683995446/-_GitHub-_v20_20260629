"""LLM 客户端，封装 OpenAI 兼容协议调用。

支持 SiliconFlow、DeepSeek、OpenAI 等兼容 OpenAI API 的服务。
遵循架构规范：适配器模式，可替换底层模型。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from shared.config import get_settings
from shared.errors import ExternalError, GeneratorError
from shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LLMResponse:
    """LLM 响应结构。"""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class LLMClient:
    """OpenAI 兼容协议 LLM 客户端。

    通过环境变量配置 provider、api_base、api_key、model。
    支持 SiliconFlow、DeepSeek、OpenAI 等。
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._api_base = self._settings.llm_api_base
        self._api_key = self._settings.llm_api_key
        self._model = self._settings.llm_model
        if not self._api_key:
            raise GeneratorError("LLM API Key 未配置", error_num=1)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._api_base,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=float(self._settings.llm_timeout),
            )
        return self._client

    @retry(
        retry=retry_if_exception_type(ExternalError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """调用 chat completions 接口。

        Args:
            messages: OpenAI 格式的消息列表
            temperature: 采样温度，None 则用配置默认值
            max_tokens: 最大输出 token，None 则用配置默认值
            **kwargs: 其他传递给 API 的参数

        Returns:
            LLMResponse 结构
        """
        client = await self._get_client()
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": (
                temperature if temperature is not None else self._settings.llm_temperature
            ),
            "max_tokens": max_tokens or self._settings.llm_max_tokens,
            **kwargs,
        }

        logger.debug(
            "llm_request",
            model=self._model,
            message_count=len(messages),
        )

        try:
            resp = await client.post("/chat/completions", json=payload)
        except httpx.RequestError as e:
            raise ExternalError(f"LLM 请求失败: {e}", code="20001") from e

        if resp.status_code == 429:
            raise ExternalError("LLM API 限流", code="20002")
        if resp.status_code == 401:
            raise GeneratorError("LLM API Key 无效", error_num=2)
        if resp.status_code != 200:
            raise ExternalError(
                f"LLM API 异常: {resp.status_code} {resp.text[:200]}",
                code="20003",
            )

        data = resp.json()
        choice = data["choices"][0]
        content = choice["message"]["content"]
        usage = data.get("usage", {})

        response = LLMResponse(
            content=content,
            model=data.get("model", self._model),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

        logger.info(
            "llm_response",
            model=response.model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            content_length=len(response.content),
        )

        return response

    async def close(self) -> None:
        """关闭客户端。"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
