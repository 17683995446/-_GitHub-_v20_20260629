-- GitCast 数据库初始化脚本
-- 在 PostgreSQL 容器首次启动时自动执行

-- 启用 UUID 扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 启用 pg_trgm 扩展（全文搜索优化）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 创建索引（SQLAlchemy 也会创建，这里做幂等保障）
-- projects 表索引
CREATE INDEX IF NOT EXISTS ix_projects_repo_url ON projects (repo_url);
CREATE INDEX IF NOT EXISTS ix_projects_full_name ON projects (full_name);
CREATE INDEX IF NOT EXISTS ix_projects_stars ON projects (stars DESC);
CREATE INDEX IF NOT EXISTS ix_projects_language ON projects (language);

-- articles 表索引
CREATE INDEX IF NOT EXISTS ix_articles_status ON articles (status);
CREATE INDEX IF NOT EXISTS ix_articles_created_at ON articles (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_articles_project_id ON articles (project_id);

-- audio 表索引
CREATE INDEX IF NOT EXISTS ix_audio_article_id ON audio (article_id);
CREATE INDEX IF NOT EXISTS ix_audio_status ON audio (status);

-- publishes 表索引
CREATE INDEX IF NOT EXISTS ix_publishes_article_id ON publishes (article_id);
CREATE INDEX IF NOT EXISTS ix_publishes_platform ON publishes (platform);
CREATE INDEX IF NOT EXISTS ix_publishes_status ON publishes (status);

-- users 表索引
CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);
CREATE INDEX IF NOT EXISTS ix_users_api_key ON users (api_key);

-- subscriptions 表索引
CREATE INDEX IF NOT EXISTS ix_subscriptions_user_id ON subscriptions (user_id);

-- 全文搜索索引（用于文章搜索）
CREATE INDEX IF NOT EXISTS ix_articles_title_trgm ON articles USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_projects_description_trgm ON projects USING gin (description gin_trgm_ops);
