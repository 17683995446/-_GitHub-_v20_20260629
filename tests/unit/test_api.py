"""API 端点测试。"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.app import create_app
from api.deps import get_db


@pytest.fixture
def app(mock_settings: None, tmp_path: str, monkeypatch: pytest.MonkeyPatch):
    """创建测试用 FastAPI 应用。"""
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path))
    monkeypatch.setenv("STORAGE_BASE_URL", "http://test.local/storage")
    from shared.config import get_settings

    get_settings.cache_clear()
    return create_app()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    """创建测试用 HTTP 客户端。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealthCheck:
    """健康检查端点测试。"""

    @pytest.mark.asyncio
    async def test_health(self, client: AsyncClient) -> None:
        """健康检查应返回 200。"""
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "gitcast"

    @pytest.mark.asyncio
    async def test_health_ready(self, client: AsyncClient) -> None:
        """就绪检查应返回 200。"""
        resp = await client.get("/api/v1/health/ready")
        assert resp.status_code == 200


class TestPipelineAPI:
    """管线 API 端点测试。"""

    @pytest.mark.asyncio
    async def test_run_pipeline_async(
        self, app, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """异步触发管线应返回 job_id。"""
        # Mock 后台任务执行
        from services.orchestrator.job_tracker import get_job_tracker

        tracker = get_job_tracker()

        # 清理之前测试的 job
        tracker._jobs.clear()

        resp = await client.post(
            "/api/v1/pipeline/run",
            json={"max_results": 3, "generate_audio": False},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "accepted"

        # 验证 job 已注册
        job = tracker.get_job(data["job_id"])
        assert job is not None

        # 清理后台任务
        tracker.cancel_job(data["job_id"])
        tracker._jobs.clear()

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, client: AsyncClient) -> None:
        """查询不存在的 job 应返回 404。"""
        resp = await client.get("/api/v1/pipeline/jobs/nonexistent-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, client: AsyncClient) -> None:
        """空任务列表应返回空数组。"""
        from services.orchestrator.job_tracker import get_job_tracker

        tracker = get_job_tracker()
        tracker._jobs.clear()

        resp = await client.get("/api/v1/pipeline/jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_jobs_with_data(self, client: AsyncClient) -> None:
        """有任务时应返回列表。"""
        from datetime import datetime, timezone

        from services.orchestrator.job_tracker import get_job_tracker
        from services.orchestrator.pipeline import JobStatus, PipelineResult

        tracker = get_job_tracker()
        tracker._jobs.clear()

        # 手动注册一个已完成任务
        result = PipelineResult(
            job_id="test-list-job",
            status=JobStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            total_discovered=3,
            processed=3,
            succeeded=2,
            failed=1,
            skipped=0,
        )
        tracker.update_job(result)

        resp = await client.get("/api/v1/pipeline/jobs")
        assert resp.status_code == 200
        jobs = resp.json()
        assert len(jobs) == 1
        assert jobs[0]["job_id"] == "test-list-job"
        assert jobs[0]["status"] == "completed"

        tracker._jobs.clear()

    @pytest.mark.asyncio
    async def test_run_pipeline_sync(
        self, app, client: AsyncClient, mock_settings: None
    ) -> None:
        """同步管线需要 DB，无 DB 时应优雅处理。"""
        from datetime import datetime, timezone

        from services.orchestrator.pipeline import (
            JobStatus,
            PipelineConfig,
            PipelineResult,
        )

        async def mock_run_pipeline(
            self, config: PipelineConfig, db: AsyncSession
        ) -> PipelineResult:
            return PipelineResult(
                job_id="mock-job",
                status=JobStatus.COMPLETED,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                total_discovered=0,
                processed=0,
                succeeded=0,
                failed=0,
                skipped=0,
            )

        # Mock PipelineService.run_pipeline
        from services.orchestrator import pipeline as pipeline_module

        original_run = pipeline_module.PipelineService.run_pipeline
        pipeline_module.PipelineService.run_pipeline = mock_run_pipeline  # type: ignore

        # Mock DB session
        async def mock_get_db() -> AsyncIterator[AsyncSession]:
            yield AsyncSession()  # type: ignore[call-arg]

        app.dependency_overrides[get_db] = mock_get_db

        try:
            resp = await client.post(
                "/api/v1/pipeline/run/sync",
                json={"max_results": 1, "generate_audio": False},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "completed"
        finally:
            pipeline_module.PipelineService.run_pipeline = original_run  # type: ignore
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_run_pipeline_validation_error(self, client: AsyncClient) -> None:
        """无效参数应返回 422 验证错误。"""
        resp = await client.post(
            "/api/v1/pipeline/run",
            json={"max_results": 0},  # 最小值为 1
        )
        assert resp.status_code == 422
