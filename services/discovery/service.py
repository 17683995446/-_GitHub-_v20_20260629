"""项目发现服务：整合 GitHub Search API + Trending 爬虫 + 高价值筛选。

对外提供统一接口，屏蔽内部双轨实现。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.discovery.github_client import GitHubClient
from services.discovery.project_filter import ProjectFilter, ProjectScore
from services.discovery.trending_scraper import TrendingRepo, TrendingScraper
from shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DiscoveredProject:
    """发现的项目统一结构。"""

    repo_url: str
    full_name: str
    name: str
    description: str
    language: str
    stars: int
    forks: int
    open_issues: int
    license_name: str | None
    topics: list[str]
    stars_today: int
    score: ProjectScore
    readme_excerpt: str | None
    discovery_source: str  # "search_api" | "trending"


class DiscoveryService:
    """项目发现服务。

    双轨并行策略：
    1. GitHub Search API 获取近期高星项目
    2. Trending 爬虫获取当日热榜
    3. 合并去重 + 高价值筛选
    """

    def __init__(
        self,
        github_client: GitHubClient | None = None,
        trending_scraper: TrendingScraper | None = None,
        project_filter: ProjectFilter | None = None,
    ) -> None:
        self._github = github_client
        self._trending = trending_scraper or TrendingScraper()
        self._filter = project_filter or ProjectFilter()

    async def discover(
        self,
        max_results: int = 10,
        languages: list[str] | None = None,
        trending_since: str = "daily",
    ) -> list[DiscoveredProject]:
        """执行发现流程，返回高价值项目列表。

        Args:
            max_results: 最大返回数量
            languages: 编程语言过滤列表
            trending_since: trending 时间范围

        Returns:
            去重后的高价值项目列表
        """
        # 并行获取两个来源
        search_repos: list[dict[str, Any]] = []
        trending_repos: list[TrendingRepo] = []

        # 来源1: Search API
        try:
            if self._github is None:
                self._github = GitHubClient()
            search_result = await self._github.search_repositories(
                query=self._build_search_query(languages),
                sort="stars",
                order="desc",
                per_page=30,
            )
            search_repos = search_result.get("items", [])
            logger.info("search_api_fetched", count=len(search_repos))
        except Exception as e:
            logger.warning("search_api_failed", error=str(e))

        # 来源2: Trending 爬虫
        try:
            trending_repos = await self._trending.fetch_trending(
                language=languages[0] if languages else "",
                since=trending_since,
            )
            logger.info("trending_fetched", count=len(trending_repos))
        except Exception as e:
            logger.warning("trending_fetch_failed", error=str(e))

        # 合并：trending 数据补充到 search 结果中
        stars_today_map: dict[str, int] = {}
        trending_names: set[str] = set()
        for tr in trending_repos:
            stars_today_map[tr.full_name] = tr.stars_today
            trending_names.add(tr.full_name)

        # 把 trending 中独有的项目补充到 search_repos
        existing_names = {r.get("full_name", "") for r in search_repos}
        for tr in trending_repos:
            if tr.full_name not in existing_names:
                # 用 stars_today 作为 stars 的估算值（trending 不返回总 star）
                estimated_stars = max(tr.stars_today * 50, 100)
                search_repos.append(
                    {
                        "full_name": tr.full_name,
                        "name": tr.name,
                        "description": tr.description,
                        "language": tr.language or (languages[0] if languages else ""),
                        "stargazers_count": estimated_stars,
                        "forks_count": 0,
                        "open_issues_count": 0,
                        "license": None,
                        "topics": [],
                        "pushed_at": "",  # trending 不返回，用空字符串
                        "html_url": tr.repo_url,
                    }
                )

        # 高价值筛选
        scores = self._filter.filter_high_value(
            search_repos,
            stars_today_map=stars_today_map,
            top_n=max_results,
        )

        # 构建返回结构
        results: list[DiscoveredProject] = []
        for score in scores:
            repo_data = next(
                (r for r in search_repos if r.get("full_name") == score.repo_full_name),
                {},
            )
            source = "trending" if score.repo_full_name in trending_names else "search_api"
            license_name = None
            if repo_data.get("license"):
                license_name = repo_data["license"].get("spdx_id")

            results.append(
                DiscoveredProject(
                    repo_url=repo_data.get("html_url", ""),
                    full_name=score.repo_full_name,
                    name=repo_data.get("name", ""),
                    description=repo_data.get("description", "") or "",
                    language=repo_data.get("language", "") or "",
                    stars=repo_data.get("stargazers_count", 0),
                    forks=repo_data.get("forks_count", 0),
                    open_issues=repo_data.get("open_issues_count", 0),
                    license_name=license_name,
                    topics=repo_data.get("topics", []),
                    stars_today=stars_today_map.get(score.repo_full_name, 0),
                    score=score,
                    readme_excerpt=None,
                    discovery_source=source,
                )
            )

        logger.info("discovery_complete", total=len(results))
        return results

    async def fetch_readme(self, owner: str, repo: str) -> str:
        """获取仓库 README（用于后续文档生成）。"""
        if self._github is None:
            self._github = GitHubClient()
        return await self._github.get_readme(owner, repo)

    async def close(self) -> None:
        """释放资源。"""
        if self._github:
            await self._github.close()
        await self._trending.close()

    def _build_search_query(self, languages: list[str] | None) -> str:
        """构建搜索查询语句。"""
        from datetime import datetime, timedelta, timezone

        # 近 90 天有更新 + Star > 500
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
        query = f"stars:>500 pushed:>{date_cutoff}"

        if languages:
            lang_filters = " ".join(f"language:{lang}" for lang in languages)
            query = f"{query} {lang_filters}"

        return query
