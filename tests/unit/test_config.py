"""配置模块单元测试。"""

from __future__ import annotations

import pytest

from shared.config import get_settings


class TestSettings:
    """配置项测试。"""

    def test_default_values(self, mock_settings: None) -> None:
        """测试默认配置值。"""
        settings = get_settings()
        assert settings.app_name == "GitCast"
        assert settings.app_env == "development"
        assert settings.app_debug is True
        assert settings.app_port == 8000

    def test_github_config(self, mock_settings: None) -> None:
        """测试 GitHub 配置。"""
        settings = get_settings()
        assert settings.github_token == "ghp_test_token"
        assert settings.github_api_base == "https://api.github.com"
        assert settings.github_api_rate_limit_per_hour == 5000

    def test_llm_config(self, mock_settings: None) -> None:
        """测试 LLM 配置。"""
        settings = get_settings()
        assert settings.llm_provider == "siliconflow"
        assert settings.llm_api_key == "sk_test_key"
        assert settings.llm_model == "Qwen/Qwen2.5-72B-Instruct"
        assert settings.llm_max_tokens == 4096

    def test_tts_config(self, mock_settings: None) -> None:
        """测试 TTS 配置。"""
        settings = get_settings()
        assert settings.tts_engine == "azure"
        assert settings.tts_voice == "zh-CN-XiaoxiaoMultilingualNeural"

    def test_environment_flags(self, mock_settings: None) -> None:
        """测试环境判断属性。"""
        settings = get_settings()
        assert settings.is_development is True
        assert settings.is_production is False

    def test_settings_singleton(self, mock_settings: None) -> None:
        """测试配置单例。"""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2


class TestSettingsEnvSwitch:
    """环境切换测试。"""

    def test_production_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试生产环境标记。"""
        monkeypatch.setenv("APP_ENV", "production")
        from shared.config import get_settings

        get_settings.cache_clear()
        settings = get_settings()
        assert settings.is_production is True
        assert settings.is_development is False
        get_settings.cache_clear()  # 清理，避免影响其他测试
