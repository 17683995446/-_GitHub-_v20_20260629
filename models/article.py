"""Article 实体：LLM 生成的解读文章。"""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, SoftDeleteMixin, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from models.audio import Audio
    from models.project import Project


class ArticleStatus(str, enum.Enum):
    """文章状态机：pending → generating → review → approved/rejected → published/archived。"""

    PENDING = "pending"
    GENERATING = "generating"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Article(Base, TimestampMixin, SoftDeleteMixin):
    """LLM 生成的通俗解读文章。"""

    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[ArticleStatus] = mapped_column(
        Enum(ArticleStatus, name="article_status"),
        default=ArticleStatus.PENDING,
        nullable=False,
    )
    llm_model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 关系
    project: Mapped[Project] = relationship("Project", back_populates="articles")
    audio: Mapped[Audio | None] = relationship(
        "Audio", back_populates="article", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Article {self.title[:30]}... status={self.status}>"
