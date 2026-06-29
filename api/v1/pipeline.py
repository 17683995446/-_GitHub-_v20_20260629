"""管线编排 API 端点。

提供管线触发和状态查询接口，供 n8n / GitHub Actions / 手动调用。
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from services.orchestrator.job_tracker import get_job_tracker
from services.orchestrator.pipeline import (
    JobStatus,
    PipelineConfig,
    PipelineService,
)
from shared.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class PipelineRunRequest(BaseModel):
    """管线触发请求。"""

    max_results: int = Field(default=5, ge=1, le=50, description="最大处理项目数")
    languages: list[str] = Field(
        default=["python", "typescript", "rust", "go"],
        description="编程语言过滤",
    )
    trending_since: str = Field(default="daily", description="trending 时间范围")
    skip_existing: bool = Field(default=True, description="跳过今天已处理的项目")
    auto_approve: bool = Field(default=True, description="自动审核通过")
    generate_audio: bool = Field(default=True, description="是否合成音频")
    publish: bool = Field(default=True, description="是否发布到多平台")


class PipelineRunResponse(BaseModel):
    """管线触发响应。"""

    job_id: str
    status: str
    message: str


class PipelineJobResponse(BaseModel):
    """管线任务状态响应。"""

    job_id: str
    status: str
    started_at: str
    finished_at: str | None
    total_discovered: int
    processed: int
    succeeded: int
    failed: int
    skipped: int
    results: list[dict[str, Any]]
    error: str | None


async def _run_pipeline_task(
    job_id: str,
    config: PipelineConfig,
) -> None:
    """后台执行管线任务。"""
    tracker = get_job_tracker()
    pipeline = PipelineService()

    from shared.database import get_session_maker

    session_maker = get_session_maker()
    async with session_maker() as db:
        try:
            result = await pipeline.run_pipeline(config, db)
            tracker.update_job(result)
        except Exception as e:
            logger.error("pipeline_task_failed", job_id=job_id, error=str(e))
            existing = tracker.get_job(job_id)
            if existing:
                existing.status = JobStatus.FAILED
                existing.error = str(e)
                tracker.update_job(existing)


@router.post("/run", response_model=PipelineRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline(request: PipelineRunRequest) -> PipelineRunResponse:
    """触发管线（异步执行）。

    立即返回 job_id，管线在后台执行。
    通过 GET /api/v1/pipeline/jobs/{job_id} 查询状态。
    """
    job_id = str(uuid.uuid4())
    tracker = get_job_tracker()
    tracker.register_job(job_id)

    config = PipelineConfig(
        max_results=request.max_results,
        languages=request.languages,
        trending_since=request.trending_since,
        skip_existing=request.skip_existing,
        auto_approve=request.auto_approve,
        generate_audio=request.generate_audio,
        publish=request.publish,
    )

    # 启动后台任务
    task = asyncio.create_task(_run_pipeline_task(job_id, config))
    tracker.track_task(job_id, task)

    logger.info("pipeline_triggered", job_id=job_id, config=config.__dict__)

    return PipelineRunResponse(
        job_id=job_id,
        status="accepted",
        message="管线已触发，请通过 GET /api/v1/pipeline/jobs/{job_id} 查询状态",
    )


@router.post("/run/sync", response_model=PipelineJobResponse)
async def run_pipeline_sync(
    request: PipelineRunRequest,
    db: AsyncSession = Depends(get_db),
) -> PipelineJobResponse:
    """同步执行管线（阻塞直到完成）。

    适用于 n8n 等外部编排器直接调用。
    """
    config = PipelineConfig(
        max_results=request.max_results,
        languages=request.languages,
        trending_since=request.trending_since,
        skip_existing=request.skip_existing,
        auto_approve=request.auto_approve,
        generate_audio=request.generate_audio,
        publish=request.publish,
    )

    pipeline = PipelineService()
    result = await pipeline.run_pipeline(config, db)

    return PipelineJobResponse(**result.to_dict())


@router.get("/jobs/{job_id}", response_model=PipelineJobResponse)
async def get_job(job_id: str) -> PipelineJobResponse:
    """查询管线任务状态。"""
    tracker = get_job_tracker()
    result = tracker.get_job(job_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {job_id}",
        )
    return PipelineJobResponse(**result.to_dict())


@router.get("/jobs", response_model=list[PipelineJobResponse])
async def list_jobs(limit: int = 20) -> list[PipelineJobResponse]:
    """列出最近的管线任务。"""
    tracker = get_job_tracker()
    jobs = tracker.list_jobs(limit=limit)
    return [PipelineJobResponse(**j.to_dict()) for j in jobs]
