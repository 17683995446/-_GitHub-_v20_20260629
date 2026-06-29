"""小宇宙发布适配器。

小宇宙是国内领先的播客平台。
使用创作者 API 上传播客音频。
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from services.publisher.base import PublishContent, Publisher, PublishResult
from shared.config import get_settings
from shared.errors import PublisherError
from shared.logging import get_logger

logger = get_logger(__name__)

XIAOYUZHOU_API_BASE = "https://api.xiaoyuzhoufm.com/v1"


class XiaoyuzhouPublisher(Publisher):
    """小宇宙发布适配器。

    流程：
    1. 上传音频文件（提供 URL）
    2. 创建播客条目
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "xiaoyuzhou"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=60.0,
                headers={
                    "Authorization": f"Bearer {self._settings.xiaoyuzhou_token}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    @retry(
        retry=retry_if_exception_type(PublisherError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def publish(self, content: PublishContent) -> PublishResult:
        """发布内容到小宇宙。"""
        client = await self._get_client()

        try:
            # 1. 上传音频
            upload_data = await self._upload_audio(client, content)

            # 2. 发布播客
            episode_data = await self._create_episode(client, content, upload_data)

            external_id = str(episode_data.get("id", ""))
            external_url = episode_data.get("url", "")

            logger.info(
                "xiaoyuzhou_published",
                episode_id=external_id,
                title=content.title,
            )
            return PublishResult(
                platform=self.name,
                external_id=external_id,
                external_url=external_url,
                success=True,
            )
        except PublisherError:
            raise
        except Exception as e:
            raise PublisherError(f"小宇宙发布失败: {e}", error_num=4) from e

    async def _upload_audio(
        self, client: httpx.AsyncClient, content: PublishContent
    ) -> dict[str, Any]:
        """上传音频文件。"""
        payload = {
            "audio_url": content.audio_url,
            "duration": content.audio_duration_sec,
        }

        try:
            resp = await client.post(
                f"{XIAOYUZHOU_API_BASE}/audio/upload",
                json=payload,
            )
        except httpx.RequestError as e:
            raise PublisherError(f"上传请求失败: {e}", error_num=5) from e

        data: dict[str, Any] = resp.json()
        if resp.status_code != 200 or data.get("code") != 0:
            raise PublisherError(
                f"上传失败: {data.get('message', '未知错误')}",
                error_num=5,
            )
        return dict(data.get("data", {}))

    async def _create_episode(
        self,
        client: httpx.AsyncClient,
        content: PublishContent,
        upload_data: dict[str, Any],
    ) -> dict[str, Any]:
        """创建播客条目。"""
        payload = {
            "audio_key": upload_data.get("audio_key", ""),
            "title": content.title,
            "description": content.body_md[:500],
            "duration": content.audio_duration_sec,
        }

        if content.tags:
            payload["tags"] = content.tags

        try:
            resp = await client.post(
                f"{XIAOYUZHOU_API_BASE}/episode/create",
                json=payload,
            )
        except httpx.RequestError as e:
            raise PublisherError(f"创建条目失败: {e}", error_num=6) from e

        data: dict[str, Any] = resp.json()
        if resp.status_code != 200 or data.get("code") != 0:
            raise PublisherError(
                f"创建条目失败: {data.get('message', '未知错误')}",
                error_num=6,
            )
        return dict(data.get("data", {}))

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
