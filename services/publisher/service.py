"""发布服务：编排多平台发布。

遵循第一性原理：错误隔离——单个平台失败不影响其他平台。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.publisher.base import PublishContent, Publisher, PublishResult
from services.publisher.factory import create_publisher, get_enabled_publishers
from shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MultiPublishResult:
    """多平台发布结果汇总。"""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: list[PublishResult] = field(default_factory=list)

    @property
    def all_succeeded(self) -> bool:
        return self.failed == 0 and self.succeeded > 0


class PublisherService:
    """发布服务。

    将一篇文章同时发布到多个平台。
    单个平台失败不影响其他平台。
    """

    def __init__(
        self,
        publishers: dict[str, Publisher] | None = None,
    ) -> None:
        self._publishers: dict[str, Publisher] = publishers or {}
        self._created_locally: list[Publisher] = []

    async def publish_to_all(
        self,
        content: PublishContent,
        platforms: list[str] | None = None,
    ) -> MultiPublishResult:
        """发布内容到所有已启用平台。

        Args:
            content: 待发布内容
            platforms: 指定平台列表，None 则使用配置中的已启用平台

        Returns:
            多平台发布结果汇总
        """
        target_platforms = (
            platforms if platforms is not None else get_enabled_publishers()
        )
        result = MultiPublishResult(total=len(target_platforms))

        logger.info(
            "publish_start",
            platforms=target_platforms,
            article=content.title,
        )

        for platform_name in target_platforms:
            publisher = self._get_publisher(platform_name)
            if publisher is None:
                logger.warning("publisher_not_available", platform=platform_name)
                result.results.append(
                    PublishResult(
                        platform=platform_name,
                        external_id=None,
                        external_url=None,
                        success=False,
                        error="发布器不可用（未配置凭据）",
                    )
                )
                result.failed += 1
                continue

            try:
                pub_result = await publisher.publish(content)
                result.results.append(pub_result)
                if pub_result.success:
                    result.succeeded += 1
                else:
                    result.failed += 1

                logger.info(
                    "publish_done",
                    platform=platform_name,
                    success=pub_result.success,
                )
            except Exception as e:
                logger.error(
                    "publish_failed",
                    platform=platform_name,
                    error=str(e),
                    exc_info=True,
                )
                result.results.append(
                    PublishResult(
                        platform=platform_name,
                        external_id=None,
                        external_url=None,
                        success=False,
                        error=str(e),
                    )
                )
                result.failed += 1

        logger.info(
            "publish_complete",
            total=result.total,
            succeeded=result.succeeded,
            failed=result.failed,
        )
        return result

    def _get_publisher(self, name: str) -> Publisher | None:
        """获取或创建发布器实例。"""
        if name in self._publishers:
            return self._publishers[name]

        try:
            publisher = create_publisher(name)
            self._publishers[name] = publisher
            self._created_locally.append(publisher)
            return publisher
        except Exception as e:
            logger.warning("publisher_create_failed", platform=name, error=str(e))
            return None

    async def close(self) -> None:
        """释放所有创建的发布器资源。"""
        for publisher in self._created_locally:
            try:
                await publisher.close()
            except Exception as e:
                logger.warning("publisher_close_failed", error=str(e))
        self._publishers.clear()
        self._created_locally.clear()
