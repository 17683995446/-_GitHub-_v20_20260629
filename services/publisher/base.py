"""发布器抽象接口。

遵循架构规范：适配器模式，每个平台一个适配器。
新增平台只需实现此接口并注册到工厂。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PublishResult:
    """发布结果。"""

    platform: str
    external_id: str | None
    external_url: str | None
    success: bool
    error: str | None = None


@dataclass
class PublishContent:
    """待发布内容。"""

    article_id: str
    title: str
    body_md: str
    audio_url: str
    audio_duration_sec: int
    cover_image_url: str | None = None
    tags: list[str] | None = None


class Publisher(ABC):
    """发布器抽象接口。

    所有平台实现（喜马拉雅、小宇宙、B站、微信）都必须实现此接口。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """平台名称。"""
        ...

    @abstractmethod
    async def publish(self, content: PublishContent) -> PublishResult:
        """发布内容到平台。

        Args:
            content: 待发布内容（文章 + 音频 URL）

        Returns:
            发布结果
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """释放资源。"""
        ...
