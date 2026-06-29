"""B站发布适配器。

通过B站 API 上传视频播客内容。
使用 Cookie 认证（SESSDATA + bili_jct/csrf）。
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

BILIBILI_API_BASE = "https://api.bilibili.com"


class BilibiliPublisher(Publisher):
    """B站发布适配器。

    流程：
    1. 上传音频/视频文件
    2. 提交稿件（视频投稿）
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "bilibili"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=120.0,
                cookies={
                    "SESSDATA": self._settings.bilibili_sessdata,
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; GitCast/0.1)",
                    "Referer": "https://www.bilibili.com",
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
        """发布内容到B站。"""
        client = await self._get_client()

        try:
            # 1. 预上传（获取上传参数）
            pre_upload_data = await self._pre_upload(client, content)

            # 2. 上传音频文件
            upload_data = await self._upload_file(client, content, pre_upload_data)

            # 3. 提交稿件
            submit_data = await self._submit(client, content, upload_data)

            bvid = str(submit_data.get("bvid", ""))
            external_url = f"https://www.bilibili.com/video/{bvid}" if bvid else None

            logger.info(
                "bilibili_published",
                bvid=bvid,
                title=content.title,
            )
            return PublishResult(
                platform=self.name,
                external_id=bvid,
                external_url=external_url,
                success=True,
            )
        except PublisherError:
            raise
        except Exception as e:
            raise PublisherError(f"B站发布失败: {e}", error_num=7) from e

    async def _pre_upload(
        self, client: httpx.AsyncClient, content: PublishContent
    ) -> dict[str, Any]:
        """预上传，获取上传参数。"""
        params: dict[str, str] = {
            "name": f"{content.title}.mp3",
            "size": "0",
            "csrf": self._settings.bilibili_csrf,
        }

        try:
            resp = await client.get(
                f"{BILIBILI_API_BASE}/preupload",
                params=params,
            )
        except httpx.RequestError as e:
            raise PublisherError(f"预上传失败: {e}", error_num=8) from e

        data: dict[str, Any] = resp.json()
        if resp.status_code != 200 or data.get("code") != 0:
            raise PublisherError(
                f"预上传失败: {data.get('message', '未知错误')}",
                error_num=8,
            )
        return dict(data.get("data", {}))

    async def _upload_file(
        self,
        client: httpx.AsyncClient,
        content: PublishContent,
        pre_upload: dict[str, Any],
    ) -> dict[str, Any]:
        """上传音频文件。

        提供音频 URL，B站服务端自行下载。
        """
        payload = {
            "audio_url": content.audio_url,
            "endpoints": pre_upload.get("endpoints", ""),
            "auth": pre_upload.get("auth", ""),
            "biz_id": pre_upload.get("biz_id", ""),
            "csrf": self._settings.bilibili_csrf,
        }

        try:
            resp = await client.post(
                f"{BILIBILI_API_BASE}/x/vu/web/add/v3",
                json=payload,
            )
        except httpx.RequestError as e:
            raise PublisherError(f"上传失败: {e}", error_num=9) from e

        data: dict[str, Any] = resp.json()
        if resp.status_code != 200 or data.get("code") != 0:
            raise PublisherError(
                f"上传失败: {data.get('message', '未知错误')}",
                error_num=9,
            )
        return dict(data.get("data", {}))

    async def _submit(
        self,
        client: httpx.AsyncClient,
        content: PublishContent,
        upload_data: dict[str, Any],
    ) -> dict[str, Any]:
        """提交稿件。"""
        payload = {
            "copyright": 1,  # 自制
            "videos": [
                {
                    "filename": upload_data.get("filename", ""),
                    "title": content.title,
                    "desc": content.body_md[:250],
                }
            ],
            "source": "GitCast 自动生成",
            "tag": ",".join(content.tags) if content.tags else "科技,播客",
            "csrf": self._settings.bilibili_csrf,
        }

        try:
            resp = await client.post(
                f"{BILIBILI_API_BASE}/x/vu/web/add/v3",
                json=payload,
            )
        except httpx.RequestError as e:
            raise PublisherError(f"提交稿件失败: {e}", error_num=10) from e

        data: dict[str, Any] = resp.json()
        if resp.status_code != 200 or data.get("code") != 0:
            raise PublisherError(
                f"提交稿件失败: {data.get('message', '未知错误')}",
                error_num=10,
            )
        return dict(data.get("data", {}))

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
