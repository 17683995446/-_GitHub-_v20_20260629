"""发布适配器 HTTP 层单元测试（使用 respx 模拟）。"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from services.publisher.base import PublishContent
from services.publisher.wechat_adapter import WeChatPublisher
from services.publisher.xiaoyuzhou_adapter import XiaoyuzhouPublisher


def make_content() -> PublishContent:
    """创建测试用发布内容。"""
    return PublishContent(
        article_id="test-article-id",
        title="测试文章标题",
        body_md="# 测试文章\n\n这是一段测试内容。" * 20,
        audio_url="http://test.local/storage/test.mp3",
        audio_duration_sec=120,
    )


class TestXiaoyuzhouAdapter:
    """小宇宙适配器测试。"""

    @pytest.mark.asyncio
    @respx.mock
    async def test_publish_success(self, mock_settings: None) -> None:
        """成功发布到小宇宙。"""
        # Mock 上传音频
        respx.post("https://api.xiaoyuzhoufm.com/v1/audio/upload").mock(
            return_value=Response(
                200,
                json={"code": 0, "data": {"audio_key": "test-key"}},
            )
        )
        # Mock 创建条目
        respx.post("https://api.xiaoyuzhoufm.com/v1/episode/create").mock(
            return_value=Response(
                200,
                json={
                    "code": 0,
                    "data": {"id": "ep-123", "url": "https://xyz.fm/ep/123"},
                },
            )
        )

        publisher = XiaoyuzhouPublisher()
        result = await publisher.publish(make_content())

        assert result.success is True
        assert result.platform == "xiaoyuzhou"
        assert result.external_id == "ep-123"
        assert "xyz.fm" in (result.external_url or "")
        await publisher.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_publish_api_error(self, mock_settings: None) -> None:
        """API 返回错误。"""
        respx.post("https://api.xiaoyuzhoufm.com/v1/audio/upload").mock(
            return_value=Response(200, json={"code": 1001, "message": "token 无效"})
        )

        publisher = XiaoyuzhouPublisher()
        from shared.errors import PublisherError

        with pytest.raises(PublisherError, match="上传失败"):
            await publisher.publish(make_content())
        await publisher.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_publish_network_error(self, mock_settings: None) -> None:
        """网络错误应重试后报错。"""
        import httpx

        respx.post("https://api.xiaoyuzhoufm.com/v1/audio/upload").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        publisher = XiaoyuzhouPublisher()
        from shared.errors import PublisherError

        with pytest.raises(PublisherError):
            await publisher.publish(make_content())
        await publisher.close()


class TestWeChatAdapter:
    """微信公众号适配器测试。"""

    @pytest.mark.asyncio
    @respx.mock
    async def test_publish_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """成功发布到微信。"""
        monkeypatch.setenv("WECHAT_APP_ID", "test-app-id")
        monkeypatch.setenv("WECHAT_APP_SECRET", "test-secret")
        from shared.config import get_settings

        get_settings.cache_clear()

        # Mock 获取 access_token
        respx.get("https://api.weixin.qq.com/cgi-bin/token").mock(
            return_value=Response(
                200,
                json={"access_token": "test-token-123", "expires_in": 7200},
            )
        )
        # Mock 创建图文
        respx.post("https://api.weixin.qq.com/cgi-bin/media/addnews").mock(
            return_value=Response(200, json={"media_id": "media-abc-123"})
        )
        # Mock 发布
        respx.post("https://api.weixin.qq.com/cgi-bin/freepublish/submit").mock(
            return_value=Response(
                200,
                json={"errcode": 0, "errmsg": "ok", "publish_id": "pub-456"},
            )
        )

        publisher = WeChatPublisher()
        result = await publisher.publish(make_content())

        assert result.success is True
        assert result.platform == "wechat"
        assert result.external_id == "media-abc-123"
        await publisher.close()
        get_settings.cache_clear()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_token_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """获取 access_token 失败。"""
        monkeypatch.setenv("WECHAT_APP_ID", "test-app-id")
        monkeypatch.setenv("WECHAT_APP_SECRET", "wrong-secret")
        from shared.config import get_settings

        get_settings.cache_clear()

        respx.get("https://api.weixin.qq.com/cgi-bin/token").mock(
            return_value=Response(
                200,
                json={"errcode": 40013, "errmsg": "invalid appid"},
            )
        )

        publisher = WeChatPublisher()
        from shared.errors import PublisherError

        with pytest.raises(PublisherError, match="access_token"):
            await publisher.publish(make_content())
        await publisher.close()
        get_settings.cache_clear()

    def test_md_to_html(self) -> None:
        """Markdown 转 HTML。"""
        publisher = WeChatPublisher()
        html = publisher._md_to_html("# 标题\n\n段落内容")
        assert "<h1>" in html
        assert "<p>" in html
        assert "标题" in html
