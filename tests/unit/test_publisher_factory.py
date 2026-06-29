"""发布器工厂单元测试。"""

from __future__ import annotations

import pytest

from services.publisher.base import PublishContent, Publisher, PublishResult
from services.publisher.factory import (
    create_publisher,
    get_enabled_publishers,
    register_publisher,
)


class MockPublisher(Publisher):
    """用于测试的 mock 发布器。"""

    @property
    def name(self) -> str:
        return "mock"

    async def publish(self, content: PublishContent) -> PublishResult:
        return PublishResult(
            platform="mock",
            external_id="mock-id",
            external_url="https://mock.example.com/mock-id",
            success=True,
        )

    async def close(self) -> None:
        pass


class TestPublisherFactory:
    """发布器工厂测试。"""

    @pytest.fixture(autouse=True)
    def _clear_registry(self) -> None:
        """每个测试前后清理注册表。"""
        import services.publisher.factory as factory_module

        factory_module._PUBLISHER_REGISTRY.clear()
        yield
        factory_module._PUBLISHER_REGISTRY.clear()

    def test_register_and_create(self) -> None:
        """注册并创建发布器。"""
        register_publisher("mock", MockPublisher)
        publisher = create_publisher("mock")
        assert publisher.name == "mock"
        assert isinstance(publisher, MockPublisher)

    def test_unknown_publisher_raises(self) -> None:
        """未知平台应报错。"""
        from shared.errors import PublisherError

        with pytest.raises(PublisherError, match="未知"):
            create_publisher("nonexistent")

    def test_get_enabled_publishers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """获取已启用平台列表。"""
        monkeypatch.setenv("ENABLED_PUBLISHERS", "ximalaya,wechat")
        from shared.config import get_settings

        get_settings.cache_clear()
        publishers = get_enabled_publishers()
        assert "ximalaya" in publishers
        assert "wechat" in publishers
        get_settings.cache_clear()

    def test_get_enabled_publishers_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """空配置返回空列表。"""
        monkeypatch.setenv("ENABLED_PUBLISHERS", "")
        from shared.config import get_settings

        get_settings.cache_clear()
        publishers = get_enabled_publishers()
        assert publishers == []
        get_settings.cache_clear()
