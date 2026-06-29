"""数据统计 API 端点。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db
from models.article import Article
from models.audio import Audio
from models.project import Project
from models.publish import Publish, PublishStatus
from models.user import User

router = APIRouter(prefix="/stats", tags=["stats"])


class OverviewResponse(BaseModel):
    """仪表盘概览。"""

    total_projects: int = 0
    total_articles: int = 0
    total_audio: int = 0
    total_publishes: int = 0
    articles_today: int = 0
    articles_this_week: int = 0
    publish_success_rate: float = 0.0
    by_status: dict[str, int] = {}
    by_language: dict[str, int] = {}


class PlatformStats(BaseModel):
    """平台发布统计。"""

    platform: str
    total: int = 0
    success: int = 0
    failed: int = 0
    success_rate: float = 0.0


class ArticleTrendItem(BaseModel):
    """文章趋势项。"""

    date: str
    count: int


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OverviewResponse:
    """获取仪表盘概览数据。"""
    # 总数统计
    total_projects = await db.scalar(select(func.count(Project.id))) or 0
    total_articles = await db.scalar(select(func.count(Article.id))) or 0
    total_audio = await db.scalar(select(func.count(Audio.id))) or 0
    total_publishes = await db.scalar(select(func.count(Publish.id))) or 0

    # 今日和本周文章数
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_start = today_start - timedelta(days=7)

    articles_today = await db.scalar(
        select(func.count(Article.id)).where(Article.created_at >= today_start)
    ) or 0

    articles_this_week = await db.scalar(
        select(func.count(Article.id)).where(Article.created_at >= week_start)
    ) or 0

    # 按状态统计
    status_result = await db.execute(
        select(Article.status, func.count(Article.id))
        .group_by(Article.status)
    )
    by_status = {
        (s.value if s else "unknown"): c
        for s, c in status_result.all()
    }

    # 按语言统计（通过 join Project）
    lang_result = await db.execute(
        select(Project.language, func.count(Article.id))
        .join(Article, Article.project_id == Project.id)
        .group_by(Project.language)
    )
    by_language = {
        (lang or "unknown"): count
        for lang, count in lang_result.all()
    }

    # 发布成功率
    success_count = await db.scalar(
        select(func.count(Publish.id)).where(Publish.status == PublishStatus.SUCCESS)
    ) or 0
    publish_success_rate = (
        (success_count / total_publishes * 100) if total_publishes > 0 else 0.0
    )

    return OverviewResponse(
        total_projects=total_projects,
        total_articles=total_articles,
        total_audio=total_audio,
        total_publishes=total_publishes,
        articles_today=articles_today,
        articles_this_week=articles_this_week,
        publish_success_rate=round(publish_success_rate, 2),
        by_status=by_status,
        by_language=by_language,
    )


@router.get("/platforms", response_model=list[PlatformStats])
async def get_platform_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PlatformStats]:
    """获取各平台发布统计。"""
    result = await db.execute(
        select(
            Publish.platform,
            func.count(Publish.id).label("total"),
            func.count(Publish.id).filter(
                Publish.status == PublishStatus.SUCCESS
            ).label("success"),
            func.count(Publish.id).filter(
                Publish.status == PublishStatus.FAILED
            ).label("failed"),
        )
        .group_by(Publish.platform)
    )

    stats: list[PlatformStats] = []
    for row in result.all():
        platform = row.platform.value if row.platform else "unknown"
        total = row.total or 0
        success = row.success or 0
        failed = row.failed or 0
        rate = (success / total * 100) if total > 0 else 0.0
        stats.append(
            PlatformStats(
                platform=platform,
                total=total,
                success=success,
                failed=failed,
                success_rate=round(rate, 2),
            )
        )

    return stats


@router.get("/articles/trend", response_model=list[ArticleTrendItem])
async def get_article_trend(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ArticleTrendItem]:
    """获取文章生成趋势（最近 N 天）。"""
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(
            func.date_trunc("day", Article.created_at).label("date"),
            func.count(Article.id).label("count"),
        )
        .where(Article.created_at >= start_date)
        .group_by("date")
        .order_by("date")
    )

    return [
        ArticleTrendItem(
            date=row.date.isoformat() if row.date else "",
            count=row[1] or 0,
        )
        for row in result.all()
    ]
