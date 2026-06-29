"""User 实体：用户与认证。"""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, SoftDeleteMixin, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from models.subscription import Subscription


class UserRole(str, enum.Enum):
    """用户角色。"""

    ADMIN = "admin"
    USER = "user"
    API = "api"  # B端 API 用户


class User(Base, TimestampMixin, SoftDeleteMixin):
    """用户实体。"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"),
        default=UserRole.USER,
        nullable=False,
    )
    api_key: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # 关系
    subscription: Mapped[list[Subscription]] = relationship(
        "Subscription", back_populates="user", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_users_email_active", "email", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role.value})>"
