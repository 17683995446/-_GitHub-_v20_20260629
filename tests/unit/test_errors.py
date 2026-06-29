"""错误体系单元测试。"""

from __future__ import annotations

from shared.errors import (
    BusinessError,
    ConfigError,
    DiscoveryError,
    ExternalError,
    GeneratorError,
    GitCastError,
    PublisherError,
    SystemError,
    TTSError,
)


class TestErrorHierarchy:
    """错误继承关系测试。"""

    def test_base_error(self) -> None:
        err = GitCastError("test", "UNKNOWN")
        assert err.message == "test"
        assert err.code == "UNKNOWN"

    def test_business_error(self) -> None:
        err = BusinessError("参数错误", "10001")
        assert isinstance(err, GitCastError)
        assert err.code == "10001"

    def test_system_error(self) -> None:
        err = SystemError("数据库连接失败")
        assert isinstance(err, GitCastError)
        assert err.code == "SYSTEM"

    def test_external_error(self) -> None:
        err = ExternalError("GitHub API 超时")
        assert isinstance(err, GitCastError)
        assert err.code == "EXTERNAL"

    def test_config_error_inherits_system(self) -> None:
        err = ConfigError("缺少必填配置")
        assert isinstance(err, SystemError)
        assert isinstance(err, GitCastError)
        assert err.code == "CONFIG"


class TestModuleErrorCodes:
    """各模块错误码格式测试。"""

    def test_discovery_error_code(self) -> None:
        err = DiscoveryError("未找到项目", error_num=1)
        assert err.code == "10001"
        assert isinstance(err, BusinessError)

    def test_generator_error_code(self) -> None:
        err = GeneratorError("LLM 拒绝生成", error_num=5)
        assert err.code == "20005"
        assert isinstance(err, BusinessError)

    def test_tts_error_code(self) -> None:
        err = TTSError("TTS 超时", error_num=3)
        assert err.code == "30003"
        assert isinstance(err, ExternalError)

    def test_publisher_error_code(self) -> None:
        err = PublisherError("发布到小宇宙失败", error_num=2)
        assert err.code == "40002"
        assert isinstance(err, ExternalError)

    def test_orchestrator_error_code(self) -> None:
        from shared.errors import OrchestratorError

        err = OrchestratorError("管线编排失败", error_num=1)
        assert err.code == "50001"
        assert isinstance(err, SystemError)

    def test_error_codes_are_unique(self) -> None:
        """确保不同模块的码不冲突。"""
        from shared.errors import OrchestratorError

        codes = [
            DiscoveryError("a", 1).code,
            GeneratorError("b", 1).code,
            TTSError("c", 1).code,
            PublisherError("d", 1).code,
            OrchestratorError("e", 1).code,
        ]
        assert len(set(codes)) == 5
