"""Publish 实体：多平台发布记录。"""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, SoftDeleteMixin, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from models.article import Article


class PublishPlatform(str, enum.Enum):
    """发布平台枚举。"""

    XIMALAYA = "ximalaya"
    XIAOYUZHOU = "xiaoyuzhou"
    BILIBILI = "bilibili"
    WECHAT = "wechat"


class PublishStatus(str, enum.Enum):
    """发布状态机：pending → publishing → success/failed。"""

    PENDING = "pending"
    PUBLISHING = "publishing"
    SUCCESS = "success"
    FAILED = "failed"


class Publish(Base, TimestampMixin, SoftDeleteMixin):
    """多平台发布记录。"""

    __tablename__ = "publishes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False
    )
    platform: Mapped[PublishPlatform] = mapped_column(
        Enum(PublishPlatform, name="publish_platform"),
        nullable=False,
    )
    external_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[PublishStatus] = mapped_column(
        Enum(PublishStatus, name="publish_status"),
        default=PublishStatus.PENDING,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # 关系
    article: Mapped[Article] = relationship("Article")

    def __repr__(self) -> str:
        return f"<Publish platform={self.platform} status={self.status}>"
