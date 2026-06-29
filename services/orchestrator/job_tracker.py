"""管线任务追踪器。

简化设计：内存存储，进程重启后丢失。
生产环境应替换为 Redis/DB 后端。
"""

from __future__ import annotations

import asyncio

from services.orchestrator.pipeline import JobStatus, PipelineResult
from shared.logging import get_logger

logger = get_logger(__name__)


class JobTracker:
    """管线任务追踪器。

    管理异步管线任务的状态，供 API 层查询。
    """

    def __init__(self) -> None:
        self._jobs: dict[str, PipelineResult] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def get_job(self, job_id: str) -> PipelineResult | None:
        """获取任务状态。"""
        return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 20) -> list[PipelineResult]:
        """列出最近的任务。"""
        jobs = sorted(
            self._jobs.values(),
            key=lambda j: j.started_at,
            reverse=True,
        )
        return jobs[:limit]

    def register_job(self, job_id: str) -> PipelineResult:
        """注册新任务（PENDING 状态）。"""
        from datetime import datetime, timezone

        result = PipelineResult(
            job_id=job_id,
            status=JobStatus.PENDING,
            started_at=datetime.now(timezone.utc),
        )
        self._jobs[job_id] = result
        return result

    def update_job(self, result: PipelineResult) -> None:
        """更新任务状态。"""
        self._jobs[result.job_id] = result

    def track_task(self, job_id: str, task: asyncio.Task[None]) -> None:
        """关联异步任务。"""
        self._tasks[job_id] = task

    def cancel_job(self, job_id: str) -> bool:
        """取消任务。"""
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def clear_completed(self) -> int:
        """清理已完成任务，返回清理数量。"""
        completed_ids = [
            jid for jid, result in self._jobs.items()
            if result.status in (JobStatus.COMPLETED, JobStatus.FAILED)
        ]
        for jid in completed_ids:
            self._jobs.pop(jid, None)
            self._tasks.pop(jid, None)
        return len(completed_ids)


# 全局单例
_job_tracker: JobTracker | None = None


def get_job_tracker() -> JobTracker:
    """获取全局任务追踪器单例。"""
    global _job_tracker
    if _job_tracker is None:
        _job_tracker = JobTracker()
    return _job_tracker
