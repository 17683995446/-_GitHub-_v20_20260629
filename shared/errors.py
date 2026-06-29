"""统一错误体系。

遵循代码规范 3.5：异常分类 BusinessError / SystemError / ExternalError。
"""

from __future__ import annotations


class GitCastError(Exception):
    """所有自定义错误的基类。"""

    def __init__(self, message: str, code: str = "UNKNOWN") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class BusinessError(GitCastError):
    """业务可恢复错误。

    场景：内容审核未通过、配额超限、参数校验失败等。
    这类错误应返回给客户端，不触发告警。
    """

    def __init__(self, message: str, code: str = "BUSINESS") -> None:
        super().__init__(message, code)


class SystemError(GitCastError):
    """系统不可恢复错误。

    场景：数据库连接失败、配置缺失、内部状态不一致等。
    这类错误应触发告警并记录 ERROR 级别日志。
    """

    def __init__(self, message: str, code: str = "SYSTEM") -> None:
        super().__init__(message, code)


class ExternalError(GitCastError):
    """外部依赖故障。

    场景：GitHub API 超时、LLM API 限流、TTS 服务不可用等。
    这类错误可自动重试，连续失败触发告警。
    """

    def __init__(self, message: str, code: str = "EXTERNAL") -> None:
        super().__init__(message, code)


class ConfigError(SystemError):
    """配置错误，通常在启动时即检测到。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="CONFIG")


# ===== 业务错误码（6位数字） =====
# 格式：<模块2位><状态3位>，如 10001 = discovery模块第1个错误


class DiscoveryError(BusinessError):
    """项目发现层业务错误。"""

    def __init__(self, message: str, error_num: int = 1) -> None:
        code = f"10{error_num:03d}"
        super().__init__(message, code)


class GeneratorError(BusinessError):
    """文档生成层业务错误。"""

    def __init__(self, message: str, error_num: int = 1) -> None:
        code = f"20{error_num:03d}"
        super().__init__(message, code)


class TTSError(ExternalError):
    """音频合成层外部错误。"""

    def __init__(self, message: str, error_num: int = 1) -> None:
        code = f"30{error_num:03d}"
        super().__init__(message, code)


class PublisherError(ExternalError):
    """发布层外部错误。"""

    def __init__(self, message: str, error_num: int = 1) -> None:
        code = f"40{error_num:03d}"
        super().__init__(message, code)


class OrchestratorError(SystemError):
    """编排调度层系统错误。"""

    def __init__(self, message: str, error_num: int = 1) -> None:
        code = f"50{error_num:03d}"
        super().__init__(message, code)


class AuthError(BusinessError):
    """认证层业务错误。"""

    def __init__(self, message: str, error_num: int = 1) -> None:
        code = f"60{error_num:03d}"
        super().__init__(message, code)
