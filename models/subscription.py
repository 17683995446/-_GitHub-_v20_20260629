"""Subscription 实体：用户订阅与 API 配额。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from models.user import User


class SubscriptionPlan(str, enum.Enum):
    """订阅方案。"""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# 各方案的默认配额
PLAN_QUOTAS: dict[SubscriptionPlan, int] = {
    SubscriptionPlan.FREE: 50,
    SubscriptionPlan.PRO: 1000,
    SubscriptionPlan.ENTERPRISE: 10000,
}


class Subscription(Base, TimestampMixin):
    """用户订阅实体。"""

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan, name="subscription_plan"),
        default=SubscriptionPlan.FREE,
        nullable=False,
    )
    api_quota_per_month: Mapped[int] = mapped_column(
        Integer, default=50, nullable=False
    )
    api_used_this_month: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # 关系
    user: Mapped[User] = relationship("User", back_populates="subscription")

    @property
    def quota_remaining(self) -> int:
        """剩余配额。"""
        return max(0, self.api_quota_per_month - self.api_used_this_month)

    @property
    def quota_exceeded(self) -> bool:
        """配额是否用尽。"""
        return self.api_used_this_month >= self.api_quota_per_month

    def __repr__(self) -> str:
        return (
            f"<Subscription {self.plan.value} "
            f"(used={self.api_used_this_month}/{self.api_quota_per_month})>"
        )
