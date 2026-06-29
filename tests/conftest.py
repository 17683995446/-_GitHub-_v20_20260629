"""Pytest 公共 fixtures。"""

from __future__ import annotations

import asyncio
from collections.abc import Generator

import pytest


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """全局事件循环。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """注入测试环境变量。"""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APP_DEBUG", "true")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.setenv("LLM_API_KEY", "sk_test_key")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "test_key")
    # 清除配置缓存
    from shared.config import get_settings

    get_settings.cache_clear()
