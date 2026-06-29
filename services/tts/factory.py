"""TTS 工厂：根据配置创建引擎实例。

遵循架构规范：配置驱动，改 env 不改代码。
"""

from __future__ import annotations

from services.tts.base import TTSEngine
from shared.config import get_settings
from shared.errors import TTSError
from shared.logging import get_logger

logger = get_logger(__name__)

# 引擎注册表
_ENGINE_REGISTRY: dict[str, type[TTSEngine]] = {}


def register_engine(name: str, engine_class: type[TTSEngine]) -> None:
    """注册 TTS 引擎。"""
    _ENGINE_REGISTRY[name] = engine_class
    logger.debug("tts_engine_registered", name=name)


def create_tts_engine(engine_name: str | None = None) -> TTSEngine:
    """根据配置创建 TTS 引擎实例。

    Args:
        engine_name: 引擎名称，None 则从配置读取

    Returns:
        TTSEngine 实例

    Raises:
        TTSError: 未知的引擎名称
    """
    # 懒加载注册（避免循环导入）
    _ensure_engines_registered()

    settings = get_settings()
    name = engine_name or settings.tts_engine

    if name not in _ENGINE_REGISTRY:
        raise TTSError(
            f"未知的 TTS 引擎: {name}，可选: {list(_ENGINE_REGISTRY.keys())}",
            error_num=8,
        )

    engine = _ENGINE_REGISTRY[name]()
    logger.info("tts_engine_created", engine=name)
    return engine


def _ensure_engines_registered() -> None:
    """懒注册所有引擎。"""
    if _ENGINE_REGISTRY:
        return

    # 延迟导入避免循环依赖
    from services.tts.azure_adapter import AzureTTSAdapter
    from services.tts.cosyvoice_adapter import CosyVoiceAdapter

    register_engine("azure", AzureTTSAdapter)
    register_engine("cosyvoice", CosyVoiceAdapter)
