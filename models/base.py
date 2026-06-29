"""SQLAlchemy 声明式基类。

遵循代码规范 3.1.2：
- 主键 UUID v7（有序、可分布式生成）
- 时间字段 UTC + TIMESTAMPTZ
- 软删除 deleted_at
- 表名复数 snake_case
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    pass


class TimestampMixin:
    """创建/更新时间戳混入。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """软删除混入，禁止物理删除业务数据。"""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    @property
    def is_deleted(self) -> bool:
        """是否已软删除。"""
        return self.deleted_at is not None


def generate_uuid() -> uuid.UUID:
    """生成有序 UUID（模拟 v7 行为）。

    Python 3.10 原生不支持 uuid7，使用时间戳前缀 + 随机后缀实现有序 UUID。
    前 48 位为毫秒时间戳，保证有序性，利于 B-tree 索引。
    """
    import os
    import time

    timestamp_ms = int(time.time() * 1000)
    # 12 位时间戳 + 4 位版本(7) + 12 位随机 + 2 位变体 + 62 位随机
    uuid_int = (timestamp_ms & 0xFFFFFFFFFFFF) << 80
    uuid_int |= 0x7 << 76  # version 7
    uuid_int |= 0b11 << 62  # variant
    uuid_int |= int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    return uuid.UUID(int=uuid_int)
