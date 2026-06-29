"""高价值项目筛选器。

遵循决策 Q4：全球 Trending + 主题过滤（AI/Agent/工具/框架）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.logging import get_logger

logger = get_logger(__name__)

# 高价值主题白名单（决策 Q4）
HIGH_VALUE_TOPICS = {
    # AI / LLM
    "ai",
    "llm",
    "machine-learning",
    "deep-learning",
    "transformer",
    "natural-language-processing",
    "chatbot",
    "agent",
    "ai-agents",
    "langchain",
    "rag",
    "embedding",
    "vector-database",
    # 开发工具
    "developer-tools",
    "cli",
    "terminal",
    "ide",
    "productivity",
    "automation",
    "workflow",
    "ci-cd",
    "devops",
    # 框架与基础设施
    "framework",
    "rust",
    "go",
    "python",
    "typescript",
    "web-framework",
    "api",
    "graphql",
    "microservices",
    "database",
    "kubernetes",
    "docker",
    "observability",
    # 前沿技术
    "wasm",
    "webassembly",
    "edge-computing",
    "blockchain",
}

# 排除主题（低传播价值）
EXCLUDED_TOPICS = {
    "homework",
    "tutorial",
    "course",
    "exercise",
    "test",
    "demo",
    "example",
    " boilerplate",
}


@dataclass
class ProjectScore:
    """项目评分结果。"""

    repo_full_name: str
    total_score: float
    star_score: float
    activity_score: float
    topic_score: float
    language_score: float
    is_high_value: bool
    reasons: list[str]


class ProjectFilter:
    """高价值项目筛选器。

    多维评分：Star 数 + 活跃度 + 主题匹配 + 语言偏好。
    """

    # 评分权重
    WEIGHT_STARS = 0.35
    WEIGHT_ACTIVITY = 0.25
    WEIGHT_TOPICS = 0.25
    WEIGHT_LANGUAGE = 0.15

    # 语言偏好（中文受众最关注的语言）
    PREFERRED_LANGUAGES = {
        "python": 1.0,
        "typescript": 0.9,
        "rust": 0.85,
        "go": 0.8,
        "javascript": 0.7,
        "java": 0.6,
        "c++": 0.5,
        "c": 0.4,
        "c#": 0.4,
        "kotlin": 0.5,
        "swift": 0.4,
    }

    def score_project(
        self,
        repo_data: dict[str, Any],
        stars_today: int = 0,
    ) -> ProjectScore:
        """对单个项目评分。

        Args:
            repo_data: GitHub API 返回的仓库数据
            stars_today: 当日 Star 增量（来自 Trending）

        Returns:
            评分结果
        """
        full_name = repo_data.get("full_name", "")
        stars = repo_data.get("stargazers_count", 0)
        forks = repo_data.get("forks_count", 0)
        pushed_at = repo_data.get("pushed_at", "")
        language = repo_data.get("language", "") or ""
        topics: list[str] = repo_data.get("topics", [])
        open_issues = repo_data.get("open_issues_count", 0)
        description = repo_data.get("description", "") or ""

        reasons: list[str] = []

        # 1. Star 评分（对数缩放）
        star_score = self._score_stars(stars, stars_today)
        if stars > 10000:
            reasons.append(f"高星项目({stars:,} stars)")
        if stars_today > 100:
            reasons.append(f"当日增长{stars_today}星")

        # 2. 活跃度评分
        activity_score = self._score_activity(pushed_at, open_issues, forks)
        if activity_score > 0.8:
            reasons.append("活跃度高")

        # 3. 主题匹配评分
        topic_score, matched_topics = self._score_topics(topics, description)
        if matched_topics:
            reasons.append(f"主题匹配: {', '.join(matched_topics[:3])}")

        # 4. 语言评分
        language_score = self.PREFERRED_LANGUAGES.get(language.lower(), 0.3)
        if language.lower() in ("python", "typescript", "rust", "go"):
            reasons.append(f"热门语言({language})")

        # 加权总分
        total = (
            star_score * self.WEIGHT_STARS
            + activity_score * self.WEIGHT_ACTIVITY
            + topic_score * self.WEIGHT_TOPICS
            + language_score * self.WEIGHT_LANGUAGE
        )

        is_high_value = total >= 0.5 and not any(t.lower() in EXCLUDED_TOPICS for t in topics)

        return ProjectScore(
            repo_full_name=full_name,
            total_score=round(total, 4),
            star_score=round(star_score, 4),
            activity_score=round(activity_score, 4),
            topic_score=round(topic_score, 4),
            language_score=round(language_score, 4),
            is_high_value=is_high_value,
            reasons=reasons,
        )

    def filter_high_value(
        self,
        repos: list[dict[str, Any]],
        stars_today_map: dict[str, int] | None = None,
        top_n: int = 10,
    ) -> list[ProjectScore]:
        """从一批仓库中筛选高价值项目。

        Args:
            repos: GitHub API 返回的仓库列表
            stars_today_map: full_name → 当日 Star 增量的映射
            top_n: 返回前 N 个

        Returns:
            按总分降序排列的高价值项目列表
        """
        stars_today_map = stars_today_map or {}
        scores: list[ProjectScore] = []

        for repo in repos:
            full_name = repo.get("full_name", "")
            stars_today = stars_today_map.get(full_name, 0)
            score = self.score_project(repo, stars_today)
            if score.is_high_value:
                scores.append(score)

        scores.sort(key=lambda s: s.total_score, reverse=True)
        result = scores[:top_n]

        logger.info(
            "project_filtered",
            input_count=len(repos),
            high_value_count=len(scores),
            returned_count=len(result),
        )
        return result

    def _score_stars(self, stars: int, stars_today: int) -> float:
        """Star 评分：总量 + 增量。"""
        import math

        total_score = min(math.log10(max(stars, 1)) / 5, 1.0)
        growth_score = min(stars_today / 500, 1.0)
        # 当 stars_today 很高时，即使总量未知也能获得高分
        if stars_today > 100:
            total_score = max(total_score, 0.6)
        return total_score * 0.6 + growth_score * 0.4

    def _score_activity(self, pushed_at: str, open_issues: int, forks: int) -> float:
        """活跃度评分。"""
        from datetime import datetime, timezone

        score = 0.0
        try:
            if pushed_at:
                dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                days_ago = (datetime.now(timezone.utc) - dt).days
                if days_ago <= 7:
                    score += 0.5
                elif days_ago <= 30:
                    score += 0.3
                elif days_ago <= 90:
                    score += 0.1
        except Exception:
            pass

        # 没有数据时给基础分（trending 来源的项目本身已证明活跃）
        if not pushed_at and open_issues == 0 and forks == 0:
            score = 0.4

        if open_issues > 10:
            score += 0.25
        if forks > 100:
            score += 0.25

        return min(score, 1.0)

    def _score_topics(self, topics: list[str], description: str) -> tuple[float, list[str]]:
        """主题匹配评分。"""
        matched: list[str] = []
        desc_lower = description.lower()

        for topic in topics:
            t = topic.lower()
            if t in HIGH_VALUE_TOPICS or t in desc_lower:
                matched.append(topic)

        if not topics and not matched:
            return 0.3, []

        score = min(len(matched) / 3, 1.0) if matched else 0.2
        return score, matched
