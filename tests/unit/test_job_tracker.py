"""任务追踪器单元测试。"""

from __future__ import annotations

from services.orchestrator.job_tracker import JobTracker
from services.orchestrator.pipeline import JobStatus


class TestJobTracker:
    """任务追踪器测试。"""

    def test_register_and_get_job(self) -> None:
        """注册任务并获取。"""
        tracker = JobTracker()
        result = tracker.register_job("test-job-1")
        assert result.job_id == "test-job-1"
        assert result.status == JobStatus.PENDING

        retrieved = tracker.get_job("test-job-1")
        assert retrieved is not None
        assert retrieved.job_id == "test-job-1"
        assert retrieved.status == JobStatus.PENDING

    def test_get_nonexistent_job(self) -> None:
        """获取不存在的任务返回 None。"""
        tracker = JobTracker()
        assert tracker.get_job("nonexistent") is None

    def test_update_job(self) -> None:
        """更新任务状态。"""
        tracker = JobTracker()
        result = tracker.register_job("test-job-2")

        result.status = JobStatus.COMPLETED
        result.total_discovered = 5
        tracker.update_job(result)

        retrieved = tracker.get_job("test-job-2")
        assert retrieved is not None
        assert retrieved.status == JobStatus.COMPLETED
        assert retrieved.total_discovered == 5

    def test_list_jobs(self) -> None:
        """列出任务按时间倒序。"""
        tracker = JobTracker()
        for i in range(5):
            tracker.register_job(f"job-{i}")

        jobs = tracker.list_jobs(limit=3)
        assert len(jobs) == 3
        # 最新的应在前面（按注册顺序，后注册的应靠前）
        assert jobs[0].job_id == "job-4"

    def test_list_jobs_limit(self) -> None:
        """limit 参数应限制返回数量。"""
        tracker = JobTracker()
        for i in range(10):
            tracker.register_job(f"job-{i}")

        jobs = tracker.list_jobs(limit=5)
        assert len(jobs) == 5

    def test_clear_completed(self) -> None:
        """清理已完成的任务。"""
        tracker = JobTracker()
        # 注册3个任务
        r1 = tracker.register_job("job-1")
        r2 = tracker.register_job("job-2")
        tracker.register_job("job-3")

        # 完成前两个
        r1.status = JobStatus.COMPLETED
        r2.status = JobStatus.FAILED
        tracker.update_job(r1)
        tracker.update_job(r2)

        cleared = tracker.clear_completed()
        assert cleared == 2
        assert tracker.get_job("job-1") is None
        assert tracker.get_job("job-2") is None
        assert tracker.get_job("job-3") is not None

    def test_get_tracker_singleton(self) -> None:
        """全局追踪器应为单例。"""
        from services.orchestrator.job_tracker import get_job_tracker

        tracker1 = get_job_tracker()
        tracker2 = get_job_tracker()
        assert tracker1 is tracker2
