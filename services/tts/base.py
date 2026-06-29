"""TTS 引擎抽象接口。

遵循架构规范：适配器模式，所有 TTS 实现都实现此接口。
切换引擎只需改配置，不改业务代码。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SynthesisResult:
    """TTS 合成结果。"""

    audio_data: bytes
    duration_sec: float
    sample_rate: int
    format: str  # "mp3" | "wav" | "ogg"
    engine: str
    voice_id: str


class TTSEngine(ABC):
    """TTS 引擎抽象接口。

    所有 TTS 实现（Azure、CosyVoice2、edge-tts）都必须实现此接口。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """引擎名称。"""
        ...

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        speed: float = 1.0,
    ) -> SynthesisResult:
        """将文本合成为音频。

        Args:
            text: 待合成文本（建议单段不超过 3000 字符）
            voice_id: 音色 ID，None 用默认音色
            speed: 语速倍率（0.5-2.0）

        Returns:
            合成结果
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """释放资源。"""
        ...
