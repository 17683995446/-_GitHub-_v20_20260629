"""结构化日志模块，基于 structlog。

遵循代码规范 3.6：结构化日志 JSON 格式，必含 trace_id。
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from structlog.types import EventDict, Processor


def _add_app_context(_logger: Any, _method_name: str, event_dict: EventDict) -> EventDict:
    """注入应用级上下文字段。"""
    event_dict["app"] = "gitcast"
    return event_dict


def setup_logging(log_level: str = "INFO") -> None:
    """初始化日志系统，应在应用启动时调用一次。

    Args:
        log_level: 日志级别，如 DEBUG / INFO / WARNING / ERROR
    """
    # 标准 library logging 配置（structlog 底层依赖）
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    # structlog 共享处理器链
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_app_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors + [structlog.processors.JSONRenderer()],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """获取一个结构化 logger 实例。

    Args:
        name: logger 名称，通常传 __name__

    Returns:
        BoundLogger 实例，支持 .info() / .error() / .debug() 等方法
    """
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def bind_context(**kwargs: Any) -> None:
    """绑定上下文变量，后续所有日志自动携带。

    典型用法：在请求中间件中绑定 trace_id、user_id。
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """清除上下文变量，应在请求结束时调用。"""
    structlog.contextvars.clear_contextvars()
