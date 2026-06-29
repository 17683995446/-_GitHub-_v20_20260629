"""管线编排服务：整合发现 → 生成 → 合成 → 持久化。

遵循架构规范：4 层解耦设计，编排层只做流程串联，不包含业务逻辑。
遵循第一性原理：错误隔离——单个项目失败不影响整体管线。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.article import Article, ArticleStatus
from models.audio import Audio, AudioStatus
from models.project import Project
from models.publish import Publish, PublishStatus
from services.discovery.service import DiscoveredProject, DiscoveryService
from services.generator.service import GeneratedArticle, GeneratorService
from services.publisher.base import PublishContent
from services.publisher.service import PublisherService
from services.storage.base import StorageBackend
from services.storage.factory import get_storage_backend
from services.tts.service import AudioOutput, TTSService
from shared.config import get_settings
from shared.errors import OrchestratorError
from shared.logging import get_logger

logger = get_logger(__name__)


class JobStatus(str, Enum):
    """管线任务状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PipelineConfig:
    """管线运行配置。"""

    max_results: int = 5
    languages: list[str] = field(
        default_factory=lambda: ["python", "typescript", "rust", "go"]
    )
    trending_since: str = "daily"
    skip_existing: bool = True
    auto_approve: bool = True
    generate_audio: bool = True
    publish: bool = True


@dataclass
class ProjectResult:
    """单个项目处理结果。"""

    project_name: str
    status: str  # success / failed / skipped
    error: str | None = None
    article_title: str | None = None
    article_id: str | None = None
    audio_duration: float | None = None
    audio_id: str | None = None
    published_platforms: list[str] | None = None


@dataclass
class PipelineResult:
    """管线运行结果。"""

    job_id: str
    status: JobStatus
    started_at: datetime
    finished_at: datetime | None = None
    total_discovered: int = 0
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[ProjectResult] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（API 响应用）。"""
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "total_discovered": self.total_discovered,
            "processed": self.processed,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": [
                {
                    "project_name": r.project_name,
                    "status": r.status,
                    "error": r.error,
                    "article_title": r.article_title,
                    "article_id": r.article_id,
                    "audio_duration": r.audio_duration,
                    "audio_id": r.audio_id,
                    "published_platforms": r.published_platforms,
                }
                for r in self.results
            ],
            "error": self.error,
        }


class PipelineService:
    """管线编排服务。

    编排流程：
    1. 发现高价值项目（DiscoveryService）
    2. 逐个项目处理：
       a. 幂等检查（今天是否已处理过）
       b. 持久化 Project 实体
       c. 生成文章（GeneratorService）
       d. 持久化 Article 实体
       e. 合成音频（TTSService）
       f. 保存音频文件 + 持久化 Audio 实体
    3. 返回汇总结果
    """

    def __init__(
        self,
        discovery_service: DiscoveryService | None = None,
        generator_service: GeneratorService | None = None,
        tts_service: TTSService | None = None,
        storage: StorageBackend | None = None,
        publisher_service: PublisherService | None = None,
    ) -> None:
        self._discovery = discovery_service
        self._generator = generator_service
        self._tts = tts_service
        self._storage = storage
        self._publisher = publisher_service
        self._settings = get_settings()

    async def run_pipeline(
        self,
        config: PipelineConfig,
        db: AsyncSession,
    ) -> PipelineResult:
        """执行完整管线。

        Args:
            config: 管线配置
            db: 数据库会话

        Returns:
            管线运行结果
        """
        job_id = str(uuid.uuid4())
        result = PipelineResult(
            job_id=job_id,
            status=JobStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )

        logger.info(
            "pipeline_started",
            job_id=job_id,
            max_results=config.max_results,
            languages=config.languages,
        )

        try:
            # 阶段1：发现项目
            projects = await self._discover(config)
            result.total_discovered = len(projects)
            logger.info("pipeline_discovery_done", job_id=job_id, count=len(projects))

            # 阶段2：逐个项目处理
            for project in projects:
                project_result = await self._process_project(project, config, db)
                result.results.append(project_result)
                result.processed += 1

                if project_result.status == "success":
                    result.succeeded += 1
                elif project_result.status == "skipped":
                    result.skipped += 1
                else:
                    result.failed += 1

                logger.info(
                    "pipeline_project_done",
                    job_id=job_id,
                    project=project_result.project_name,
                    status=project_result.status,
                )

            result.status = JobStatus.COMPLETED

        except Exception as e:
            result.status = JobStatus.FAILED
            result.error = str(e)
            logger.error("pipeline_failed", job_id=job_id, error=str(e), exc_info=True)
        finally:
            result.finished_at = datetime.now(timezone.utc)
            await self._cleanup()

        logger.info(
            "pipeline_completed",
            job_id=job_id,
            status=result.status.value,
            succeeded=result.succeeded,
            failed=result.failed,
            skipped=result.skipped,
            duration=(result.finished_at - result.started_at).total_seconds(),
        )

        return result

    async def _discover(self, config: PipelineConfig) -> list[DiscoveredProject]:
        """执行项目发现。"""
        if self._discovery is None:
            self._discovery = DiscoveryService()

        try:
            return await self._discovery.discover(
                max_results=config.max_results,
                languages=config.languages,
                trending_since=config.trending_since,
            )
        except Exception as e:
            logger.error("pipeline_discovery_failed", error=str(e))
            raise OrchestratorError(f"项目发现失败: {e}", error_num=1) from e

    async def _process_project(
        self,
        project: DiscoveredProject,
        config: PipelineConfig,
        db: AsyncSession,
    ) -> ProjectResult:
        """处理单个项目：幂等检查 → 持久化 → 生成 → 合成。"""
        result = ProjectResult(project_name=project.full_name, status="success")

        try:
            # 幂等检查：今天是否已处理过
            if config.skip_existing:
                existing = await self._check_existing(project.full_name, db)
                if existing:
                    result.status = "skipped"
                    result.article_title = existing
                    logger.info("pipeline_project_skipped", project=project.full_name)
                    return result

            # 持久化 Project
            project_entity = await self._save_project(project, db)

            # 生成文章
            article = await self._generate_article(project, config)
            result.article_title = article.title

            # 持久化 Article
            article_entity = await self._save_article(
                project_entity.id, article, config, db
            )
            result.article_id = str(article_entity.id)

            # 合成音频
            if config.generate_audio:
                audio_output = await self._synthesize_audio(article)
                result.audio_duration = audio_output.duration_sec

                # 保存音频文件 + 持久化 Audio
                audio_entity = await self._save_audio(
                    article_entity.id, audio_output, project.full_name, db
                )
                result.audio_id = str(audio_entity.id)

                # 发布到多平台
                if config.publish:
                    published = await self._publish_content(
                        article_entity, audio_entity, db
                    )
                    if published:
                        result.published_platforms = published

            await db.commit()

        except Exception as e:
            await db.rollback()
            result.status = "failed"
            result.error = str(e)
            logger.error(
                "pipeline_project_failed",
                project=project.full_name,
                error=str(e),
                exc_info=True,
            )

        return result

    async def _check_existing(
        self,
        full_name: str,
        db: AsyncSession,
    ) -> str | None:
        """检查今天是否已为该项目生成过文章。

        Returns:
            已有文章标题（如已存在），否则 None
        """
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        stmt = (
            select(Article)
            .join(Project, Article.project_id == Project.id)
            .where(Project.full_name == full_name)
            .where(Article.created_at >= today_start)
            .where(Article.status.in_([ArticleStatus.APPROVED, ArticleStatus.PUBLISHED]))
            .limit(1)
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        return existing.title if existing else None

    async def _save_project(
        self,
        project: DiscoveredProject,
        db: AsyncSession,
    ) -> Project:
        """持久化 Project 实体。"""
        # 先查找是否已存在
        stmt = select(Project).where(Project.repo_url == project.repo_url)
        existing = (await db.execute(stmt)).scalar_one_or_none()

        if existing:
            # 更新元数据
            existing.stars = project.stars
            existing.forks = project.forks
            existing.open_issues = project.open_issues
            existing.last_synced_at = datetime.now(timezone.utc)
            return existing

        entity = Project(
            repo_url=project.repo_url,
            name=project.name,
            full_name=project.full_name,
            description=project.description,
            language=project.language,
            stars=project.stars,
            forks=project.forks,
            open_issues=project.open_issues,
            license_name=project.license_name,
            topics=json.dumps(project.topics, ensure_ascii=False) if project.topics else None,
            last_synced_at=datetime.now(timezone.utc),
            discovery_source=project.discovery_source,
        )
        db.add(entity)
        await db.flush()
        return entity

    async def _generate_article(
        self,
        project: DiscoveredProject,
        config: PipelineConfig,
    ) -> GeneratedArticle:
        """调用 GeneratorService 生成文章。"""
        if self._generator is None:
            self._generator = GeneratorService()

        # 根据项目规模选择文章长度
        project_size = self._determine_project_size(project)

        return await self._generator.generate(
            repo_name=project.name,
            repo_full_name=project.full_name,
            repo_description=project.description,
            repo_language=project.language,
            repo_stars=project.stars,
            repo_license=project.license_name or "未指定",
            repo_url=project.repo_url,
            readme_excerpt=project.readme_excerpt,
            project_size=project_size,
        )

    def _determine_project_size(self, project: DiscoveredProject) -> str:
        """根据项目规模确定文章长度档位。"""
        if project.stars > 10000:
            return "large"
        if project.stars > 2000:
            return "medium"
        return "small"

    async def _save_article(
        self,
        project_id: uuid.UUID,
        article: GeneratedArticle,
        config: PipelineConfig,
        db: AsyncSession,
    ) -> Article:
        """持久化 Article 实体。"""
        status = ArticleStatus.APPROVED if config.auto_approve else ArticleStatus.REVIEW

        entity = Article(
            project_id=project_id,
            title=article.title,
            body_md=article.body_md,
            word_count=article.word_count,
            status=status,
            llm_model=article.llm_model,
            prompt_version=article.prompt_version,
        )
        db.add(entity)
        await db.flush()
        return entity

    async def _synthesize_audio(self, article: GeneratedArticle) -> AudioOutput:
        """调用 TTSService 合成音频。"""
        if self._tts is None:
            self._tts = TTSService()

        return await self._tts.synthesize_article(article.body_md)

    async def _save_audio(
        self,
        article_id: uuid.UUID,
        audio: AudioOutput,
        project_name: str,
        db: AsyncSession,
    ) -> Audio:
        """保存音频文件并持久化 Audio 实体。"""
        if self._storage is None:
            self._storage = get_storage_backend()

        # 生成文件名：audios/<project_name>/<article_id>.mp3
        safe_name = project_name.replace("/", "_")
        filename = f"audios/{safe_name}/{article_id}.mp3"
        stored = await self._storage.save(audio.audio_data, filename)

        entity = Audio(
            article_id=article_id,
            file_url=stored.file_url,
            duration_sec=int(audio.duration_sec),
            file_size_bytes=stored.file_size,
            voice_id=audio.voice_id,
            tts_engine=audio.engine,
            status=AudioStatus.READY,
        )
        db.add(entity)
        await db.flush()
        return entity

    async def _publish_content(
        self,
        article: Article,
        audio: Audio,
        db: AsyncSession,
    ) -> list[str]:
        """发布内容到多平台。

        Returns:
            成功发布的平台名称列表
        """
        if self._publisher is None:
            self._publisher = PublisherService()

        content = PublishContent(
            article_id=str(article.id),
            title=article.title,
            body_md=article.body_md,
            audio_url=audio.file_url,
            audio_duration_sec=audio.duration_sec,
        )

        try:
            result = await self._publisher.publish_to_all(content)
            published = [r.platform for r in result.results if r.success]

            # 持久化发布记录
            for pub_result in result.results:
                publish_entity = Publish(
                    article_id=article.id,
                    platform=pub_result.platform,
                    status=PublishStatus.SUCCESS if pub_result.success else PublishStatus.FAILED,
                    external_id=pub_result.external_id,
                    external_url=pub_result.external_url,
                    error_message=pub_result.error,
                )
                db.add(publish_entity)

            await db.flush()
            return published
        except Exception as e:
            logger.error("publish_error", error=str(e), exc_info=True)
            return []

    async def _cleanup(self) -> None:
        """释放资源。"""
        if self._discovery:
            await self._discovery.close()
            self._discovery = None
        if self._generator:
            await self._generator.close()
            self._generator = None
        if self._tts:
            await self._tts.close()
            self._tts = None
        if self._publisher:
            await self._publisher.close()
            self._publisher = None
