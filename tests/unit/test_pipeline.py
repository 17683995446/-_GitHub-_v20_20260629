"""管线编排服务单元测试。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.discovery.project_filter import ProjectScore
from services.discovery.service import DiscoveredProject
from services.generator.service import GeneratedArticle
from services.orchestrator.pipeline import (
    JobStatus,
    PipelineConfig,
    PipelineResult,
    PipelineService,
)
from services.storage.base import StoredFile
from services.tts.service import AudioOutput


def make_mock_project(
    full_name: str = "owner/repo",
    stars: int = 5000,
) -> DiscoveredProject:
    """创建模拟发现项目。"""
    return DiscoveredProject(
        repo_url=f"https://github.com/{full_name}",
        full_name=full_name,
        name=full_name.split("/")[-1],
        description="A test project",
        language="Python",
        stars=stars,
        forks=100,
        open_issues=10,
        license_name="MIT",
        topics=["ai", "llm"],
        stars_today=50,
        score=ProjectScore(
            repo_full_name=full_name,
            total_score=0.85,
            star_score=0.9,
            activity_score=0.8,
            topic_score=0.7,
            language_score=0.9,
            is_high_value=True,
            reasons=["高星项目", "活跃度高"],
        ),
        readme_excerpt="Test README content",
        discovery_source="search_api",
    )


def make_mock_article(title: str = "测试文章标题") -> GeneratedArticle:
    """创建模拟生成文章。"""
    return GeneratedArticle(
        title=title,
        body_md=f"# {title}\n\n这是一段测试内容。" * 20,
        word_count=500,
        llm_model="test-model",
        prompt_version="0.1.0",
        prompt_tokens=1000,
        completion_tokens=2000,
        total_tokens=3000,
    )


def make_mock_audio() -> AudioOutput:
    """创建模拟音频输出。"""
    return AudioOutput(
        audio_data=b"fake_mp3_data",
        duration_sec=120.5,
        format="mp3",
        engine="azure",
        voice_id="zh-CN-XiaoxiaoMultilingualNeural",
        segment_count=5,
        total_chars=3000,
    )


class MockDiscoveryService:
    """模拟发现服务。"""

    def __init__(self, projects: list[DiscoveredProject] | None = None) -> None:
        self._projects = projects if projects is not None else [make_mock_project()]

    async def discover(
        self,
        max_results: int = 5,
        languages: list[str] | None = None,
        trending_since: str = "daily",
    ) -> list[DiscoveredProject]:
        return self._projects[:max_results]

    async def close(self) -> None:
        pass


class MockGeneratorService:
    """模拟生成服务。"""

    async def generate(self, **kwargs) -> GeneratedArticle:
        return make_mock_article()

    async def close(self) -> None:
        pass


class MockTTSService:
    """模拟 TTS 服务。"""

    async def synthesize_article(
        self,
        text: str,
        voice_id: str | None = None,
        speed: float = 1.0,
    ) -> AudioOutput:
        return make_mock_audio()

    async def close(self) -> None:
        pass


class MockStorageBackend:
    """模拟存储后端。"""

    async def save(
        self,
        data: bytes,
        filename: str,
        content_type: str = "audio/mpeg",
    ) -> StoredFile:
        return StoredFile(
            filename=filename,
            file_url=f"http://test.local/storage/{filename}",
            file_size=len(data),
            content_type=content_type,
        )

    async def exists(self, filename: str) -> bool:
        return False

    async def delete(self, filename: str) -> None:
        pass

    async def get_url(self, filename: str) -> str:
        return f"http://test.local/storage/{filename}"


class MockDBSession:
    """模拟异步数据库会话。"""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False
        self.rolled_back = False
        self._entities: dict[str, object] = {}

    async def execute(self, stmt):
        """模拟查询，返回空结果。"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        return mock_result

    def add(self, entity) -> None:
        """模拟添加实体。"""
        self.added.append(entity)
        # 模拟 flush 分配 ID
        if not hasattr(entity, "id") or entity.id is None:
            entity.id = uuid.uuid4()

    async def flush(self) -> None:
        """模拟 flush。"""

    async def commit(self) -> None:
        """模拟 commit。"""
        self.committed = True

    async def rollback(self) -> None:
        """模拟 rollback。"""
        self.rolled_back = True

    async def close(self) -> None:
        """模拟 close。"""


class TestPipelineConfig:
    """管线配置测试。"""

    def test_default_config(self) -> None:
        """默认配置应有合理值。"""
        config = PipelineConfig()
        assert config.max_results == 5
        assert config.skip_existing is True
        assert config.auto_approve is True
        assert config.generate_audio is True

    def test_custom_config(self) -> None:
        """自定义配置应正确设置。"""
        config = PipelineConfig(
            max_results=10,
            languages=["rust"],
            skip_existing=False,
        )
        assert config.max_results == 10
        assert config.languages == ["rust"]
        assert config.skip_existing is False


class TestPipelineResult:
    """管线结果测试。"""

    def test_to_dict(self) -> None:
        """结果应可序列化为字典。"""
        result = PipelineResult(
            job_id="test-job",
            status=JobStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            total_discovered=3,
            processed=3,
            succeeded=2,
            failed=1,
            skipped=0,
        )
        d = result.to_dict()
        assert d["job_id"] == "test-job"
        assert d["status"] == "completed"
        assert d["succeeded"] == 2
        assert d["failed"] == 1


class TestPipelineService:
    """管线服务测试。"""

    @pytest.mark.asyncio
    async def test_run_pipeline_success(self, mock_settings: None) -> None:
        """完整管线应成功运行。"""
        projects = [
            make_mock_project("owner1/repo1", stars=5000),
            make_mock_project("owner2/repo2", stars=3000),
        ]

        pipeline = PipelineService(
            discovery_service=MockDiscoveryService(projects),
            generator_service=MockGeneratorService(),
            tts_service=MockTTSService(),
            storage=MockStorageBackend(),
        )

        config = PipelineConfig(max_results=2)
        db = MockDBSession()

        result = await pipeline.run_pipeline(config, db)  # type: ignore[arg-type]

        assert result.status == JobStatus.COMPLETED
        assert result.total_discovered == 2
        assert result.processed == 2
        assert result.succeeded == 2
        assert result.failed == 0
        assert len(result.results) == 2
        assert all(r.status == "success" for r in result.results)
        assert db.committed is True

    @pytest.mark.asyncio
    async def test_pipeline_error_isolation(self, mock_settings: None) -> None:
        """单个项目失败不影响其他项目。"""
        projects = [
            make_mock_project("good/repo", stars=5000),
            make_mock_project("bad/repo", stars=3000),
        ]

        # 生成器第二次调用时抛异常
        class FailingGenerator(MockGeneratorService):
            def __init__(self) -> None:
                self._call_count = 0

            async def generate(self, **kwargs) -> GeneratedArticle:
                self._call_count += 1
                if self._call_count == 2:
                    raise RuntimeError("LLM API 超时")
                return make_mock_article()

        pipeline = PipelineService(
            discovery_service=MockDiscoveryService(projects),
            generator_service=FailingGenerator(),
            tts_service=MockTTSService(),
            storage=MockStorageBackend(),
        )

        config = PipelineConfig(max_results=2)
        db = MockDBSession()

        result = await pipeline.run_pipeline(config, db)  # type: ignore[arg-type]

        assert result.status == JobStatus.COMPLETED
        assert result.succeeded == 1
        assert result.failed == 1
        assert result.results[0].status == "success"
        assert result.results[1].status == "failed"
        assert "LLM API 超时" in (result.results[1].error or "")

    @pytest.mark.asyncio
    async def test_pipeline_skip_audio(self, mock_settings: None) -> None:
        """generate_audio=False 时不合成音频。"""
        project = make_mock_project()

        tts = MockTTSService()
        tts.synthesize_article = AsyncMock(return_value=make_mock_audio())  # type: ignore

        pipeline = PipelineService(
            discovery_service=MockDiscoveryService([project]),
            generator_service=MockGeneratorService(),
            tts_service=tts,
            storage=MockStorageBackend(),
        )

        config = PipelineConfig(max_results=1, generate_audio=False)
        db = MockDBSession()

        result = await pipeline.run_pipeline(config, db)  # type: ignore[arg-type]

        assert result.succeeded == 1
        tts.synthesize_article.assert_not_called()
        assert result.results[0].audio_duration is None

    @pytest.mark.asyncio
    async def test_pipeline_empty_discovery(self, mock_settings: None) -> None:
        """无项目发现时管线正常完成。"""
        pipeline = PipelineService(
            discovery_service=MockDiscoveryService([]),
            generator_service=MockGeneratorService(),
            tts_service=MockTTSService(),
            storage=MockStorageBackend(),
        )

        config = PipelineConfig()
        db = MockDBSession()

        result = await pipeline.run_pipeline(config, db)  # type: ignore[arg-type]

        assert result.status == JobStatus.COMPLETED
        assert result.total_discovered == 0
        assert result.processed == 0
        assert result.succeeded == 0

    @pytest.mark.asyncio
    async def test_project_size_determination(self, mock_settings: None) -> None:
        """根据 star 数确定文章长度档位。"""
        pipeline = PipelineService(
            discovery_service=MockDiscoveryService(),
            generator_service=MockGeneratorService(),
            tts_service=MockTTSService(),
            storage=MockStorageBackend(),
        )

        large = make_mock_project(stars=20000)
        medium = make_mock_project(stars=5000)
        small = make_mock_project(stars=500)

        assert pipeline._determine_project_size(large) == "large"
        assert pipeline._determine_project_size(medium) == "medium"
        assert pipeline._determine_project_size(small) == "small"
