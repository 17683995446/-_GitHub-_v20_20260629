"""GitHub API 客户端，封装 Search API 和仓库元数据获取。

遵循架构规范 2.2：外部依赖通过适配器封装，可替换。
遵循代码规范 3.5：外部错误自动重试（tenacity）。
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from shared.config import get_settings
from shared.errors import DiscoveryError, ExternalError
from shared.logging import get_logger

logger = get_logger(__name__)


class GitHubClient:
    """GitHub REST API 客户端。

    封装认证、限流、重试逻辑，对外提供简洁的查询接口。
    """

    def __init__(self, token: str | None = None) -> None:
        self._settings = get_settings()
        self._token = token or self._settings.github_token
        if not self._token:
            raise ExternalError("GitHub token 未配置", code="10002")
        self._base_url = self._settings.github_api_base
        self._headers = {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitCast/0.1",
        }
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._headers,
                timeout=30.0,
            )
        return self._client

    @retry(
        retry=retry_if_exception_type(ExternalError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """发送 GitHub API 请求，带重试。"""
        client = await self._get_client()
        url = f"{self._base_url}{path}"
        logger.debug("github_api_request", url=url, params=params)

        try:
            resp = await client.get(url, params=params)
        except httpx.RequestError as e:
            raise ExternalError(f"GitHub API 请求失败: {e}", code="10003") from e

        # 限流处理
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining is not None and int(remaining) < 100:
            logger.warning("github_rate_limit_low", remaining=remaining)

        if resp.status_code == 403:
            reset_at = resp.headers.get("X-RateLimit-Reset", "unknown")
            raise ExternalError(f"GitHub API 限流，重置时间: {reset_at}", code="10004")
        if resp.status_code == 404:
            raise DiscoveryError("未找到指定资源", error_num=2)
        if resp.status_code != 200:
            raise ExternalError(
                f"GitHub API 异常: {resp.status_code} {resp.text[:200]}",
                code="10005",
            )

        data: dict[str, Any] = resp.json()
        return data

    async def search_repositories(
        self,
        query: str = "stars:>1000",
        sort: str = "stars",
        order: str = "desc",
        per_page: int = 30,
        page: int = 1,
    ) -> dict[str, Any]:
        """搜索仓库。

        Args:
            query: 搜索查询语句，如 "stars:>1000 language:python pushed:>2026-01-01"
            sort: 排序方式：stars / forks / updated
            order: 排序方向：desc / asc
            per_page: 每页数量（最大 100）
            page: 页码

        Returns:
            GitHub Search API 响应，含 total_count 和 items
        """
        return await self._request(
            "/search/repositories",
            params={
                "q": query,
                "sort": sort,
                "order": order,
                "per_page": per_page,
                "page": page,
            },
        )

    async def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        """获取单个仓库的详细信息。"""
        return await self._request(f"/repos/{owner}/{repo}")

    async def get_readme(self, owner: str, repo: str) -> str:
        """获取仓库 README 内容（纯文本）。"""
        client = await self._get_client()
        url = f"{self._base_url}/repos/{owner}/{repo}/readme"
        try:
            readme_headers = {**self._headers, "Accept": "application/vnd.github.raw"}
            resp = await client.get(url, headers=readme_headers)
        except httpx.RequestError as e:
            raise ExternalError(f"获取 README 失败: {e}", code="10006") from e

        if resp.status_code == 404:
            raise DiscoveryError("仓库无 README", error_num=3)
        if resp.status_code != 200:
            raise ExternalError(f"获取 README 异常: {resp.status_code}", code="10006")

        return resp.text

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
