"""ProjectFilter 单元测试。"""

from __future__ import annotations

from services.discovery.project_filter import ProjectFilter


class TestProjectFilter:
    """高价值项目筛选器测试。"""

    def setup_method(self) -> None:
        self.filter = ProjectFilter()

    def test_high_star_project_scores_high(self) -> None:
        """高星项目应获得高分。"""
        repo = {
            "full_name": "langchain-ai/langchain",
            "stargazers_count": 95000,
            "forks_count": 15000,
            "open_issues_count": 500,
            "pushed_at": "2026-06-28T10:00:00Z",
            "language": "Python",
            "topics": ["ai", "llm", "agent", "langchain"],
            "description": "Building applications with LLMs",
        }
        score = self.filter.score_project(repo, stars_today=300)
        assert score.is_high_value is True
        assert score.total_score > 0.5
        assert any("主题匹配" in r or "高星" in r or "热门" in r for r in score.reasons)

    def test_low_quality_project_filtered_out(self) -> None:
        """低质量项目应被过滤。"""
        repo = {
            "full_name": "user/homework-demo",
            "stargazers_count": 5,
            "forks_count": 0,
            "open_issues_count": 0,
            "pushed_at": "2026-01-01T00:00:00Z",
            "language": "",
            "topics": ["homework", "demo"],
            "description": "My homework",
        }
        score = self.filter.score_project(repo)
        assert score.is_high_value is False

    def test_trending_boost(self) -> None:
        """Trending 当日增长应提升评分。"""
        repo = {
            "full_name": "user/hot-project",
            "stargazers_count": 2000,
            "forks_count": 100,
            "open_issues_count": 30,
            "pushed_at": "2026-06-28T00:00:00Z",
            "language": "Rust",
            "topics": ["framework", "rust"],
            "description": "A fast framework",
        }
        score_no_boost = self.filter.score_project(repo, stars_today=0)
        score_with_boost = self.filter.score_project(repo, stars_today=400)
        assert score_with_boost.total_score > score_no_boost.total_score

    def test_language_preference(self) -> None:
        """Python/TS/Rust/Go 应获得更高语言分。"""
        py_repo = {
            "full_name": "a/b",
            "stargazers_count": 1000,
            "forks_count": 50,
            "open_issues_count": 10,
            "pushed_at": "2026-06-28T00:00:00Z",
            "language": "Python",
            "topics": ["python"],
            "description": "A Python tool",
        }
        cobol_repo = py_repo.copy()
        cobol_repo["language"] = "COBOL"
        cobol_repo["full_name"] = "c/d"
        cobol_repo["topics"] = []

        py_score = self.filter.score_project(py_repo)
        cobol_score = self.filter.score_project(cobol_repo)
        assert py_score.language_score > cobol_score.language_score

    def test_filter_high_value_returns_sorted(self) -> None:
        """filter_high_value 应按分数降序返回。"""
        repos = [
            {
                "full_name": "a/low",
                "stargazers_count": 600,
                "forks_count": 20,
                "open_issues_count": 5,
                "pushed_at": "2026-06-28T00:00:00Z",
                "language": "Python",
                "topics": ["ai"],
                "description": "Low stars AI project",
            },
            {
                "full_name": "b/high",
                "stargazers_count": 50000,
                "forks_count": 5000,
                "open_issues_count": 200,
                "pushed_at": "2026-06-28T00:00:00Z",
                "language": "TypeScript",
                "topics": ["ai", "llm", "agent"],
                "description": "High stars AI agent",
            },
        ]
        results = self.filter.filter_high_value(repos, top_n=10)
        assert len(results) >= 1
        assert results[0].total_score >= results[-1].total_score
        assert results[0].repo_full_name == "b/high"
