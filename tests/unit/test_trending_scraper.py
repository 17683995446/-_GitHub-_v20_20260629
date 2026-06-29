"""Trending 爬虫 HTML 解析测试（不依赖网络）。"""

from __future__ import annotations

import pytest

from services.discovery.trending_scraper import TrendingScraper

# 模拟 GitHub Trending 页面 HTML 片段
MOCK_TRENDING_HTML = """
<section class="search-results">
  <div class="Box">
    <div class="Box-header"></div>
    <div class="Box-body">
      <article class="Box-row">
        <div class="d-flex flex-justify-between">
          <div class="f4 text-normal">
            <a href="/some-org/some-repo" class="Link">Some Repo</a>
          </div>
          <span class="d-inline-block float-sm-right">
            ★ 1,234 stars today
          </span>
        </div>
        <p class="col-9 color-fg-muted my-1 pr-4">
          A revolutionary AI agent framework for building LLM applications
        </p>
        <div class="f6 color-fg-muted mt-2">
          <span class="d-inline-block mr-3">
            <span itemprop="programmingLanguage">Python</span>
          </span>
        </div>
      </article>
      <article class="Box-row">
        <div class="d-flex flex-justify-between">
          <div class="f4 text-normal">
            <a href="/another/cool-project" class="Link">Cool Project</a>
          </div>
        </div>
        <p class="col-9 color-fg-muted my-1 pr-4">
          A fast Rust web framework
        </p>
      </article>
    </div>
  </div>
</section>
"""

MOCK_EMPTY_HTML = """
<section class="search-results">
  <div class="Box"><div class="Box-body"></div></div>
</section>
"""


class TestTrendingParser:
    """Trending HTML 解析器测试。"""

    def setup_method(self) -> None:
        self.scraper = TrendingScraper()

    def test_parse_valid_html(self) -> None:
        """解析正常 HTML 应返回仓库列表。"""
        repos = self.scraper._parse_trending_html(MOCK_TRENDING_HTML)
        assert len(repos) == 2

        repo1 = repos[0]
        assert repo1.full_name == "some-org/some-repo"
        assert repo1.language == "Python"
        assert repo1.stars_today > 0
        assert "AI" in repo1.description or "agent" in repo1.description

        repo2 = repos[1]
        assert "another/cool-project" in repo2.full_name or "cool-project" in repo2.name

    def test_parse_empty_html(self) -> None:
        """空 HTML 应返回空列表。"""
        repos = self.scraper._parse_trending_html(MOCK_EMPTY_HTML)
        assert repos == []

    def test_parse_malformed_html(self) -> None:
        """畸形 HTML 不应崩溃。"""
        repos = self.scraper._parse_trending_html("<html><body>not a trending page</body></html>")
        assert repos == []

    async def test_since_validation(self) -> None:
        """since 参数校验。"""
        with pytest.raises(ValueError, match="since"):
            await self.scraper.fetch_trending(since="invalid")
