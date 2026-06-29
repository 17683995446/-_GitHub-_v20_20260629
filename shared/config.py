"""集中化配置管理，基于 pydantic-settings。

所有配置项从环境变量读取，严禁硬编码。
遵循架构规范 2.1：配置外置。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，通过环境变量注入。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用
    app_name: str = Field(default="GitCast", alias="APP_NAME")
    app_env: Literal["development", "staging", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_log_level: str = Field(default="INFO", alias="APP_LOG_LEVEL")

    # GitHub
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    github_api_base: str = Field(default="https://api.github.com", alias="GITHUB_API_BASE")
    github_api_rate_limit_per_hour: int = Field(
        default=5000, alias="GITHUB_API_RATE_LIMIT_PER_HOUR"
    )

    # LLM
    llm_provider: str = Field(default="siliconflow", alias="LLM_PROVIDER")
    llm_api_base: str = Field(default="https://api.siliconflow.cn/v1", alias="LLM_API_BASE")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="Qwen/Qwen2.5-72B-Instruct", alias="LLM_MODEL")
    llm_max_tokens: int = Field(default=4096, alias="LLM_MAX_TOKENS")
    llm_temperature: float = Field(default=0.7, alias="LLM_TEMPERATURE")
    llm_timeout: int = Field(default=120, alias="LLM_TIMEOUT")

    # TTS
    tts_engine: str = Field(default="azure", alias="TTS_ENGINE")
    tts_voice: str = Field(default="zh-CN-XiaoxiaoMultilingualNeural", alias="TTS_VOICE")
    azure_speech_key: str = Field(default="", alias="AZURE_SPEECH_KEY")
    azure_speech_region: str = Field(default="eastasia", alias="AZURE_SPEECH_REGION")
    cosyvoice_api_base: str = Field(default="http://localhost:50000", alias="COSYVOICE_API_BASE")
    cosyvoice_default_voice: str = Field(default="default", alias="COSYVOICE_DEFAULT_VOICE")

    # 数据库
    database_url: str = Field(
        default="postgresql+asyncpg://gitcast:gitcast@localhost:5432/gitcast",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # 存储
    storage_type: Literal["local", "s3", "oss"] = Field(default="local", alias="STORAGE_TYPE")
    storage_local_path: str = Field(default="./storage", alias="STORAGE_LOCAL_PATH")
    storage_base_url: str = Field(default="http://localhost:8000/storage", alias="STORAGE_BASE_URL")

    # 安全
    secret_key: str = Field(default="", alias="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(
        default=30, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    jwt_refresh_token_expire_days: int = Field(default=7, alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS")

    # 发布平台
    # 喜马拉雅
    ximalaya_app_key: str = Field(default="", alias="XIMALAYA_APP_KEY")
    ximalaya_app_secret: str = Field(default="", alias="XIMALAYA_APP_SECRET")
    # 小宇宙
    xiaoyuzhou_token: str = Field(default="", alias="XIAOYUZHOU_TOKEN")
    # B站
    bilibili_sessdata: str = Field(default="", alias="BILIBILI_SESSDATA")
    bilibili_csrf: str = Field(default="", alias="BILIBILI_CSRF")
    # 微信公众号
    wechat_app_id: str = Field(default="", alias="WECHAT_APP_ID")
    wechat_app_secret: str = Field(default="", alias="WECHAT_APP_SECRET")
    # 启用的发布平台（逗号分隔）
    enabled_publishers: str = Field(
        default="ximalaya,xiaoyuzhou,bilibili,wechat",
        alias="ENABLED_PUBLISHERS",
    )

    # 业务
    daily_article_limit: int = Field(default=5, alias="DAILY_ARTICLE_LIMIT")
    free_api_quota_per_month: int = Field(default=50, alias="FREE_API_QUOTA_PER_MONTH")
    api_price_per_article: float = Field(default=0.5, alias="API_PRICE_PER_ARTICLE")
    content_review_sample_rate: float = Field(default=0.1, alias="CONTENT_REVIEW_SAMPLE_RATE")

    @property
    def is_production(self) -> bool:
        """是否生产环境。"""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        """是否开发环境。"""
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例。

    使用 lru_cache 确保整个应用生命周期只读取一次环境变量。
    测试中可通过 cache_clear() 重置。
    """
    return Settings()
