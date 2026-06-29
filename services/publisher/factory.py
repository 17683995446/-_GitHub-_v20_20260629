"""发布器工厂。

遵循架构规范：配置驱动，改 env 不改代码。
新增平台只需注册到工厂即可。
"""

from __future__ import annotations

from services.publisher.base import Publisher
from shared.config import get_settings
from shared.errors import PublisherError
from shared.logging import get_logger

logger = get_logger(__name__)

# 引擎注册表
_PUBLISHER_REGISTRY: dict[str, type[Publisher]] = {}


def register_publisher(name: str, publisher_class: type[Publisher]) -> None:
    """注册发布器。"""
    _PUBLISHER_REGISTRY[name] = publisher_class
    logger.debug("publisher_registered", name=name)


def create_publisher(name: str) -> Publisher:
    """创建指定平台的发布器实例。

    Args:
        name: 平台名称

    Returns:
        Publisher 实例

    Raises:
        PublisherError: 未知的平台名称
    """
    _ensure_publishers_registered()

    if name not in _PUBLISHER_REGISTRY:
        raise PublisherError(
            f"未知的发布平台: {name}，可选: {list(_PUBLISHER_REGISTRY.keys())}",
            error_num=15,
        )

    publisher = _PUBLISHER_REGISTRY[name]()
    logger.info("publisher_created", platform=name)
    return publisher


def get_enabled_publishers() -> list[str]:
    """获取已启用的发布平台列表。"""
    settings = get_settings()
    return [
        name.strip()
        for name in settings.enabled_publishers.split(",")
        if name.strip()
    ]


def _ensure_publishers_registered() -> None:
    """懒注册所有发布器。"""
    if _PUBLISHER_REGISTRY:
        return

    from services.publisher.bilibili_adapter import BilibiliPublisher
    from services.publisher.wechat_adapter import WeChatPublisher
    from services.publisher.xiaoyuzhou_adapter import XiaoyuzhouPublisher
    from services.publisher.ximalaya_adapter import XimalayaPublisher

    register_publisher("ximalaya", XimalayaPublisher)
    register_publisher("xiaoyuzhou", XiaoyuzhouPublisher)
    register_publisher("bilibili", BilibiliPublisher)
    register_publisher("wechat", WeChatPublisher)
