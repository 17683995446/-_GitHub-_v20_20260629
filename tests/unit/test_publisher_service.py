"""发布服务单元测试。"""

from __future__ import annotations

import pytest

from services.publisher.base import PublishContent, Publisher, PublishResult
from services.publisher.service import PublisherService


class SuccessPublisher(Publisher):
    """总是成功的发布器。"""

    def __init__(self, platform_name: str = "success") -> None:
        self._name = platform_name

    @property
    def name(self) -> str:
        return self._name

    async def publish(self, content: PublishContent) -> PublishResult:
        return PublishResult(
            platform=self._name,
            external_id=f"{self._name}-id",
            external_url=f"https://{self._name}.example.com/id",
            success=True,
        )

    async def close(self) -> None:
        pass


class FailingPublisher(Publisher):
    """总是失败的发布器。"""

    @property
    def name(self) -> str:
        return "failing"

    async def publish(self, content: PublishContent) -> PublishResult:
        raise RuntimeError("平台 API 不可用")

    async def close(self) -> None:
        pass


def make_content() -> PublishContent:
    """创建测试用发布内容。"""
    return PublishContent(
        article_id="test-article-id",
        title="测试文章标题",
        body_md="# 测试文章\n\n这是一段测试内容。" * 20,
        audio_url="http://test.local/storage/test.mp3",
        audio_duration_sec=120,
    )


class TestPublisherService:
    """发布服务测试。"""

    @pytest.mark.asyncio
    async def test_publish_all_success(self) -> None:
        """所有平台成功发布。"""
        service = PublisherService(
            publishers={
                "ximalaya": SuccessPublisher("ximalaya"),
                "wechat": SuccessPublisher("wechat"),
            }
        )

        result = await service.publish_to_all(
            make_content(),
            platforms=["ximalaya", "wechat"],
        )

        assert result.total == 2
        assert result.succeeded == 2
        assert result.failed == 0
        assert result.all_succeeded is True

    @pytest.mark.asyncio
    async def test_publish_error_isolation(self) -> None:
        """单个平台失败不影响其他平台。"""
        service = PublisherService(
            publishers={
                "ximalaya": SuccessPublisher("ximalaya"),
                "failing": FailingPublisher(),
                "wechat": SuccessPublisher("wechat"),
            }
        )

        result = await service.publish_to_all(
            make_content(),
            platforms=["ximalaya", "failing", "wechat"],
        )

        assert result.total == 3
        assert result.succeeded == 2
        assert result.failed == 1

        # 验证失败平台的错误信息
        failing_result = next(
            r for r in result.results if r.platform == "failing"
        )
        assert failing_result.success is False
        assert "API 不可用" in (failing_result.error or "")

    @pytest.mark.asyncio
    async def test_publish_all_empty_platforms(self) -> None:
        """空平台列表。"""
        service = PublisherService()

        result = await service.publish_to_all(
            make_content(),
            platforms=[],
        )

        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_publish_unavailable_platform(self) -> None:
        """不可用的平台应记录失败。"""
        service = PublisherService(publishers={})

        result = await service.publish_to_all(
            make_content(),
            platforms=["nonexistent"],
        )

        assert result.total == 1
        assert result.failed == 1
        assert "不可用" in (result.results[0].error or "")

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        """关闭应释放所有发布器。"""
        service = PublisherService(
            publishers={
                "ximalaya": SuccessPublisher("ximalaya"),
            }
        )
        await service.close()
        assert len(service._publishers) == 0

    @pytest.mark.asyncio
    async def test_publish_result_contains_external_info(self) -> None:
        """发布结果应包含外部 ID 和 URL。"""
        service = PublisherService(
            publishers={"ximalaya": SuccessPublisher("ximalaya")}
        )

        result = await service.publish_to_all(
            make_content(),
            platforms=["ximalaya"],
        )

        ximalaya_result = result.results[0]
        assert ximalaya_result.external_id == "ximalaya-id"
        assert "ximalaya.example.com" in (ximalaya_result.external_url or "")
