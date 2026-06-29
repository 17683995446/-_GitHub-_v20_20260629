"""Trending 页面爬虫，获取 GitHub 非官方 Trending 榜单。

由于 GitHub 无官方 Trending API，通过爬取 HTML 页面获取。
遵循架构规范：双轨制——Search API 为主，爬虫为辅。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup

from shared.errors import ExternalError
from shared.logging import get_logger

logger = get_logger(__name__)

TRENDING_URL = "https://github.com/trending"
SINCE_OPTIONS = {"daily", "weekly", "monthly"}
LANGUAGE_OPTIONS = {
    "",
    "python",
    "javascript",
    "typescript",
    "go",
    "rust",
    "java",
    "c++",
    "c",
    "c#",
    "swift",
    "kotlin",
    "ruby",
    "php",
    "scala",
    "shell",
    "html",
    "css",
    "vue",
}


@dataclass
class TrendingRepo:
    """Trending 仓库结构。"""

    full_name: str
    name: str
    description: str
    language: str
    stars_today: int
    repo_url: str


class TrendingScraper:
    """GitHub Trending 页面爬虫。"""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; GitCast/0.1)",
                    "Accept": "text/html",
                },
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def fetch_trending(
        self,
        language: str = "",
        since: str = "daily",
    ) -> list[TrendingRepo]:
        """获取 Trending 列表。

        Args:
            language: 编程语言过滤，空字符串表示全部
            since: 时间范围：daily / weekly / monthly

        Returns:
            Trending 仓库列表
        """
        if since not in SINCE_OPTIONS:
            raise ValueError(f"since 必须是 {SINCE_OPTIONS} 之一")
        if language and language.lower() not in LANGUAGE_OPTIONS:
            raise ValueError(f"不支持的语言: {language}")

        params: dict[str, str] = {"since": since}
        if language:
            params["l"] = language.lower()

        client = await self._get_client()
        url = f"{TRENDING_URL}/{language}" if language else TRENDING_URL

        try:
            resp = await client.get(url, params=params)
        except httpx.RequestError as e:
            raise ExternalError(f"Trending 页面请求失败: {e}", code="10007") from e

        if resp.status_code != 200:
            raise ExternalError(f"Trending 页面异常: {resp.status_code}", code="10007")

        return self._parse_trending_html(resp.text)

    def _parse_trending_html(self, html: str) -> list[TrendingRepo]:
        """解析 Trending HTML 页面。"""
        soup = BeautifulSoup(html, "html.parser")
        repos: list[TrendingRepo] = []

        articles = soup.select("article.Box-row")
        for article in articles:
            repo = self._parse_article(article)
            if repo:
                repos.append(repo)

        logger.info("trending_parsed", count=len(repos))
        return repos

    def _parse_article(self, article: Any) -> TrendingRepo | None:
        """解析单个仓库条目。"""
        try:
            # GitHub Trending 页面中，仓库链接在 h2 > a 或 div.f4 > a
            link = article.select_one("h2 a") or article.select_one("a.Link")
            if not link:
                return None
            href = link.get("href", "").strip()
            # 清理 href 中可能的空格（如 "/ some / repo"）
            clean_href = "/".join(p.strip() for p in href.split("/")).strip("/")
            parts = [p for p in clean_href.split("/") if p]
            if len(parts) < 2:
                return None
            owner, name = parts[0], parts[1]
            full_name = f"{owner}/{name}"

            desc_el = article.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            lang_el = article.select_one("[itemprop='programmingLanguage']")
            language = lang_el.get_text(strip=True) if lang_el else ""

            stars_today = 0
            stars_el = article.select("span.d-inline-block.float-sm-right")
            for span in stars_el:
                text = span.get_text(strip=True)
                match = re.search(r"([\d,]+)\s+stars", text)
                if match:
                    stars_today = int(match.group(1).replace(",", ""))
                    break

            return TrendingRepo(
                full_name=full_name,
                name=name,
                description=description,
                language=language,
                stars_today=stars_today,
                repo_url=f"https://github.com/{full_name}",
            )
        except Exception as e:
            logger.warning("trending_parse_failed", error=str(e))
            return None

    async def close(self) -> None:
        """关闭客户端。"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
