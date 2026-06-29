"""微信公众号发布适配器。

使用微信公众号 API 发布图文消息。
流程：获取 access_token → 上传图文素材 → 发布。
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

WECHAT_API_BASE = "https://api.weixin.qq.com/cgi-bin"


class WeChatPublisher(Publisher):
    """微信公众号发布适配器。

    流程：
    1. 获取 access_token
    2. 上传封面图（如有）
    3. 创建图文素材
    4. 发布（群发或预览）
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: httpx.AsyncClient | None = None
        self._access_token: str | None = None

    @property
    def name(self) -> str:
        return "wechat"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    @retry(
        retry=retry_if_exception_type(PublisherError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def publish(self, content: PublishContent) -> PublishResult:
        """发布内容到微信公众号。"""
        client = await self._get_client()

        try:
            # 1. 获取 access_token
            token = await self._get_access_token(client)

            # 2. 创建图文素材
            media_id = await self._add_news(client, content, token)

            # 3. 发布（预览模式：发送给指定用户）
            # 生产环境使用 freepublish 接口
            publish_data = await self._freepublish(client, media_id, token)

            external_id = str(media_id)
            external_url = publish_data.get("publish_id", "")

            logger.info(
                "wechat_published",
                media_id=external_id,
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
            raise PublisherError(f"微信发布失败: {e}", error_num=11) from e

    async def _get_access_token(self, client: httpx.AsyncClient) -> str:
        """获取微信公众号 access_token。"""
        if self._access_token:
            return self._access_token

        params = {
            "grant_type": "client_credential",
            "appid": self._settings.wechat_app_id,
            "secret": self._settings.wechat_app_secret,
        }

        try:
            resp = await client.get(f"{WECHAT_API_BASE}/token", params=params)
        except httpx.RequestError as e:
            raise PublisherError(f"获取 access_token 失败: {e}", error_num=12) from e

        data = resp.json()
        if "access_token" not in data:
            raise PublisherError(
                f"获取 access_token 失败: {data.get('errmsg', '未知错误')}",
                error_num=12,
            )
        self._access_token = data["access_token"]
        return self._access_token

    async def _add_news(
        self,
        client: httpx.AsyncClient,
        content: PublishContent,
        token: str,
    ) -> str:
        """创建图文素材。"""
        # 将 Markdown 转为简单 HTML
        html_content = self._md_to_html(content.body_md)

        articles = [{
            "title": content.title,
            "content": html_content,
            "thumb_media_id": content.cover_image_url or "",
            "author": "GitCast",
            "digest": content.body_md[:120],
            "content_source_url": "",
            "need_open_comment": 0,
        }]

        payload = {"articles": articles}

        try:
            resp = await client.post(
                f"{WECHAT_API_BASE}/media/addnews",
                params={"access_token": token},
                json=payload,
            )
        except httpx.RequestError as e:
            raise PublisherError(f"创建图文失败: {e}", error_num=13) from e

        data = resp.json()
        if "media_id" not in data:
            raise PublisherError(
                f"创建图文失败: {data.get('errmsg', '未知错误')}",
                error_num=13,
            )
        return str(data["media_id"])

    async def _freepublish(
        self,
        client: httpx.AsyncClient,
        media_id: str,
        token: str,
    ) -> dict[str, Any]:
        """发布图文（免费发布接口）。"""
        payload = {"media_id": media_id}

        try:
            resp = await client.post(
                f"{WECHAT_API_BASE}/freepublish/submit",
                params={"access_token": token},
                json=payload,
            )
        except httpx.RequestError as e:
            raise PublisherError(f"发布失败: {e}", error_num=14) from e

        data: dict[str, Any] = resp.json()
        if data.get("errcode", 0) != 0:
            raise PublisherError(
                f"发布失败: {data.get('errmsg', '未知错误')}",
                error_num=14,
            )
        return data

    def _md_to_html(self, md: str) -> str:
        """简单 Markdown → HTML 转换（微信公众号兼容）。"""
        import re

        html = md
        # 标题
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        # 粗体
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        # 段落
        paragraphs = html.split("\n\n")
        html = "".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())
        return html

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
