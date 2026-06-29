"""Initial schema: all tables

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # users 表
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("admin", "user", "api", name="user_role"),
                  nullable=False, server_default="user"),
        sa.Column("api_key", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_api_key", "users", ["api_key"], unique=True)
    op.create_index("ix_users_email_active", "users", ["email", "is_active"])

    # subscriptions 表
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan", sa.Enum("free", "pro", "enterprise",
                                   name="subscription_plan"),
                  nullable=False, server_default="free"),
        sa.Column("api_quota_per_month", sa.Integer, nullable=False, server_default="50"),
        sa.Column("api_used_this_month", sa.Integer, nullable=False, server_default="0"),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])

    # projects 表
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("repo_url", sa.String(500), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("language", sa.String(50), nullable=True),
        sa.Column("stars", sa.Integer, nullable=False, server_default="0"),
        sa.Column("forks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("open_issues", sa.Integer, nullable=False, server_default="0"),
        sa.Column("license_name", sa.String(100), nullable=True),
        sa.Column("topics", sa.Text, nullable=True),
        sa.Column("discovery_source", sa.String(50), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_projects_repo_url", "projects", ["repo_url"], unique=True)
    op.create_index("ix_projects_full_name", "projects", ["full_name"])
    op.create_index("ix_projects_stars", "projects", [sa.text("stars DESC")])
    op.create_index("ix_projects_language", "projects", ["language"])

    # articles 表
    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body_md", sa.Text, nullable=False),
        sa.Column("word_count", sa.Integer, nullable=True),
        sa.Column("status", sa.Enum("pending", "generating", "review",
                                     "approved", "rejected", "published",
                                     "archived", name="article_status"),
                  nullable=False, server_default="pending"),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_articles_status", "articles", ["status"])
    op.create_index("ix_articles_created_at", "articles",
                    [sa.text("created_at DESC")])
    op.create_index("ix_articles_project_id", "articles", ["project_id"])

    # audio 表
    op.create_table(
        "audio",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("article_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("file_url", sa.String(500), nullable=False),
        sa.Column("duration_sec", sa.Integer, nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("voice_id", sa.String(100), nullable=True),
        sa.Column("tts_engine", sa.String(50), nullable=True),
        sa.Column("status", sa.Enum("pending", "synthesizing", "ready", "failed",
                                     name="audio_status"),
                  nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_audio_article_id", "audio", ["article_id"])
    op.create_index("ix_audio_status", "audio", ["status"])

    # publishes 表
    op.create_table(
        "publishes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("article_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("platform", sa.Enum("ximalaya", "xiaoyuzhou", "bilibili",
                                       "wechat", name="publish_platform"),
                  nullable=False),
        sa.Column("status", sa.Enum("pending", "publishing", "success", "failed",
                                     name="publish_status"),
                  nullable=False, server_default="pending"),
        sa.Column("external_id", sa.String(200), nullable=True),
        sa.Column("external_url", sa.String(500), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_publishes_article_id", "publishes", ["article_id"])
    op.create_index("ix_publishes_platform", "publishes", ["platform"])
    op.create_index("ix_publishes_status", "publishes", ["status"])

    # 全文搜索索引
    op.execute(
        "CREATE EXTENSION IF NOT EXISTS pg_trgm"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_articles_title_trgm "
        "ON articles USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_projects_description_trgm "
        "ON projects USING gin (description gin_trgm_ops)"
    )


def downgrade() -> None:
    op.drop_table("publishes")
    op.drop_table("audio")
    op.drop_table("articles")
    op.drop_table("projects")
    op.drop_table("subscriptions")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS user_role")
    op.execute("DROP TYPE IF EXISTS subscription_plan")
    op.execute("DROP TYPE IF EXISTS article_status")
    op.execute("DROP TYPE IF EXISTS audio_status")
    op.execute("DROP TYPE IF EXISTS publish_platform")
    op.execute("DROP TYPE IF EXISTS publish_status")
