"""内容 API 端点：文章列表、文章详情、项目列表。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db
from models.article import Article, ArticleStatus
from models.audio import Audio
from models.project import Project
from models.publish import Publish
from models.user import User

router = APIRouter(prefix="/content", tags=["content"])


class ArticleListItem(BaseModel):
    """文章列表项。"""

    id: str
    title: str
    word_count: int
    status: str
    language: str | None = None
    created_at: str
    has_audio: bool = False
    audio_duration: int | None = None


class ArticleDetail(BaseModel):
    """文章详情。"""

    id: str
    title: str
    body_md: str
    word_count: int
    status: str
    llm_model: str | None = None
    prompt_version: str | None = None
    created_at: str
    project: dict[str, Any] | None = None
    audio: dict[str, Any] | None = None
    publishes: list[dict[str, Any]] = []


class PaginatedResponse(BaseModel):
    """分页响应。"""

    items: list[Any]
    total: int
    limit: int
    offset: int


@router.get("/articles", response_model=PaginatedResponse)
async def list_articles(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: ArticleStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse:
    """获取文章列表（分页）。"""
    query = select(Article)
    count_query = select(func.count(Article.id))

    if status_filter:
        query = query.where(Article.status == status_filter)
        count_query = count_query.where(Article.status == status_filter)

    query = query.order_by(Article.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    articles = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    items: list[dict[str, Any]] = []
    for article in articles:
        # 查询是否有音频
        audio_result = await db.execute(
            select(Audio).where(Audio.article_id == article.id).limit(1)
        )
        audio = audio_result.scalar_one_or_none()

        # 获取项目信息
        project_result = await db.execute(
            select(Project).where(Project.id == article.project_id)
        )
        project = project_result.scalar_one_or_none()

        items.append(
            ArticleListItem(
                id=str(article.id),
                title=article.title,
                word_count=article.word_count or 0,
                status=article.status.value if article.status else "unknown",
                language=project.language if project else None,
                created_at=article.created_at.isoformat() if article.created_at else "",
                has_audio=audio is not None,
                audio_duration=audio.duration_sec if audio else None,
            ).model_dump()
        )

    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/articles/{article_id}", response_model=ArticleDetail)
async def get_article(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ArticleDetail:
    """获取文章详情。"""
    try:
        aid = uuid.UUID(article_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的文章 ID",
        ) from e

    result = await db.execute(
        select(Article).where(Article.id == aid)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文章不存在",
        )

    # 获取项目
    project_result = await db.execute(
        select(Project).where(Project.id == article.project_id)
    )
    project = project_result.scalar_one_or_none()
    project_data = None
    if project:
        project_data = {
            "id": str(project.id),
            "full_name": project.full_name,
            "description": project.description,
            "language": project.language,
            "stars": project.stars,
            "repo_url": project.repo_url,
        }

    # 获取音频
    audio_result = await db.execute(
        select(Audio).where(Audio.article_id == article.id)
    )
    audio = audio_result.scalar_one_or_none()
    audio_data = None
    if audio:
        audio_data = {
            "id": str(audio.id),
            "file_url": audio.file_url,
            "duration_sec": audio.duration_sec,
            "tts_engine": audio.tts_engine,
            "status": audio.status.value if audio.status else "unknown",
        }

    # 获取发布记录
    publish_result = await db.execute(
        select(Publish).where(Publish.article_id == article.id)
    )
    publishes = publish_result.scalars().all()
    publish_list = [
        {
            "platform": p.platform.value if p.platform else "unknown",
            "status": p.status.value if p.status else "unknown",
            "external_url": p.external_url,
        }
        for p in publishes
    ]

    return ArticleDetail(
        id=str(article.id),
        title=article.title,
        body_md=article.body_md,
        word_count=article.word_count or 0,
        status=article.status.value if article.status else "unknown",
        llm_model=article.llm_model,
        prompt_version=article.prompt_version,
        created_at=article.created_at.isoformat() if article.created_at else "",
        project=project_data,
        audio=audio_data,
        publishes=publish_list,
    )


@router.get("/projects", response_model=PaginatedResponse)
async def list_projects(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    language: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse:
    """获取项目列表（分页）。"""
    query = select(Project)
    count_query = select(func.count(Project.id))

    if language:
        query = query.where(Project.language == language)
        count_query = count_query.where(Project.language == language)

    query = query.order_by(Project.stars.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    projects = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    items = [
        {
            "id": str(p.id),
            "full_name": p.full_name,
            "description": p.description,
            "language": p.language,
            "stars": p.stars,
            "forks": p.forks,
            "repo_url": p.repo_url,
        }
        for p in projects
    ]

    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)
