"""TTS 工厂单元测试。"""

from __future__ import annotations

import pytest

from services.tts.base import TTSEngine
from services.tts.factory import create_tts_engine, register_engine
from shared.config import get_settings


class MockTTSAdapter(TTSEngine):
    """用于测试的 mock TTS 引擎。"""

    @property
    def name(self) -> str:
        return "mock"

    async def synthesize(self, text: str, voice_id: str | None = None, speed: float = 1.0):
        from services.tts.base import SynthesisResult

        return SynthesisResult(
            audio_data=b"mock_audio",
            duration_sec=1.0,
            sample_rate=16000,
            format="mp3",
            engine="mock",
            voice_id=voice_id or "mock-voice",
        )

    async def close(self) -> None:
        pass


class TestTTSFactory:
    """TTS 工厂测试。"""

    @pytest.fixture(autouse=True)
    def _clear_registry(self) -> None:
        """每个测试前后清理引擎注册表，保证测试隔离。"""
        import services.tts.factory as factory_module

        factory_module._ENGINE_REGISTRY.clear()
        yield
        factory_module._ENGINE_REGISTRY.clear()

    def test_register_and_create_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """注册 mock 引擎并创建。"""
        monkeypatch.setenv("TTS_ENGINE", "mock")
        get_settings.cache_clear()
        register_engine("mock", MockTTSAdapter)
        engine = create_tts_engine("mock")
        assert engine.name == "mock"
        get_settings.cache_clear()

    def test_unknown_engine_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """未知引擎应报错。"""
        monkeypatch.setenv("TTS_ENGINE", "nonexistent")
        get_settings.cache_clear()
        register_engine("mock", MockTTSAdapter)
        with pytest.raises(Exception, match="未知"):
            create_tts_engine("nonexistent")
        get_settings.cache_clear()
