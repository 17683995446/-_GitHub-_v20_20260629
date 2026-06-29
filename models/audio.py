"""Audio 实体：TTS 合成的音频文件。"""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, SoftDeleteMixin, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from models.article import Article


class AudioStatus(str, enum.Enum):
    """音频状态机：pending → synthesizing → ready/failed。"""

    PENDING = "pending"
    SYNTHESIZING = "synthesizing"
    READY = "ready"
    FAILED = "failed"


class Audio(Base, TimestampMixin, SoftDeleteMixin):
    """TTS 合成的音频文件元数据。"""

    __tablename__ = "audios"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False
    )
    file_url: Mapped[str] = mapped_column(String(512), nullable=False)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    voice_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tts_engine: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[AudioStatus] = mapped_column(
        Enum(AudioStatus, name="audio_status"),
        default=AudioStatus.PENDING,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # 关系
    article: Mapped[Article] = relationship("Article", back_populates="audio")

    def __repr__(self) -> str:
        return f"<Audio {self.file_url[:50]}... status={self.status}>"
