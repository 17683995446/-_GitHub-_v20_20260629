"""喜马拉雅发布适配器。

使用喜马拉雅开放平台 API 上传播客音频。
API 文档：https://open.ximalaya.com/
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from services.publisher.base import PublishContent, Publisher, PublishResult
from shared.config import get_settings
from shared.errors import PublisherError
from shared.logging import get_logger

logger = get_logger(__name__)

XIMALAYA_API_BASE = "https://api.ximalaya.com/openapi"


class XimalayaPublisher(Publisher):
    """喜马拉雅发布适配器。

    流程：
    1. 获取 access_token（OAuth 2.0）
    2. 上传音频文件
    3. 创建播客专辑条目
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "ximalaya"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    def _sign(self, params: dict[str, str], app_secret: str) -> str:
        """生成喜马拉雅 API 签名。"""
        sorted_keys = sorted(params.keys())
        sign_str = app_secret + "".join(f"{k}{params[k]}" for k in sorted_keys) + app_secret
        return hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()

    @retry(
        retry=retry_if_exception_type(PublisherError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def publish(self, content: PublishContent) -> PublishResult:
        """发布内容到喜马拉雅。"""
        client = await self._get_client()

        try:
            # 1. 上传音频（提供 URL，喜马拉雅自行下载）
            upload_data = await self._upload_track(client, content)

            # 2. 创建专辑条目
            track_data = await self._create_track(client, content, upload_data)

            external_id = str(track_data.get("track_id", ""))
            external_url = track_data.get("track_url", "")

            logger.info(
                "ximalaya_published",
                track_id=external_id,
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
            raise PublisherError(f"喜马拉雅发布失败: {e}", error_num=1) from e

    async def _upload_track(
        self, client: httpx.AsyncClient, content: PublishContent
    ) -> dict[str, Any]:
        """上传音频文件。"""
        params = self._build_params({
            "audio_url": content.audio_url,
            "duration": str(content.audio_duration_sec),
            "title": content.title,
        })

        try:
            resp = await client.post(f"{XIMALAYA_API_BASE}/track/upload", data=params)
        except httpx.RequestError as e:
            raise PublisherError(f"上传请求失败: {e}", error_num=2) from e

        data: dict[str, Any] = resp.json()
        if resp.status_code != 200 or data.get("ret") != 0:
            raise PublisherError(
                f"上传失败: {data.get('msg', '未知错误')}",
                error_num=2,
            )
        return dict(data.get("data", {}))

    async def _create_track(
        self,
        client: httpx.AsyncClient,
        content: PublishContent,
        upload_data: dict[str, Any],
    ) -> dict[str, Any]:
        """创建专辑条目。"""
        params = self._build_params({
            "upload_id": str(upload_data.get("upload_id", "")),
            "title": content.title,
            "intro": content.body_md[:500],
            "category_id": "20",  # 科技分类
        })

        try:
            resp = await client.post(f"{XIMALAYA_API_BASE}/track/create", data=params)
        except httpx.RequestError as e:
            raise PublisherError(f"创建条目失败: {e}", error_num=3) from e

        data: dict[str, Any] = resp.json()
        if resp.status_code != 200 or data.get("ret") != 0:
            raise PublisherError(
                f"创建条目失败: {data.get('msg', '未知错误')}",
                error_num=3,
            )
        return dict(data.get("data", {}))

    def _build_params(self, extra: dict[str, str]) -> dict[str, str]:
        """构建带签名的 API 参数。"""
        app_key = self._settings.ximalaya_app_key
        app_secret = self._settings.ximalaya_app_secret

        params = {
            "app_key": app_key,
            "timestamp": str(int(time.time())),
            **extra,
        }
        params["sign"] = self._sign(params, app_secret)
        return params

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
