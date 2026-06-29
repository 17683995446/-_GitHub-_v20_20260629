"""TTS 合成服务：整合分段器 + 引擎 + 音频拼接。

对外提供统一接口：传入长文本，输出完整音频。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from services.tts.base import SynthesisResult, TTSEngine
from services.tts.factory import create_tts_engine
from services.tts.segmenter import TextSegmenter
from shared.errors import TTSError
from shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AudioOutput:
    """完整音频输出。"""

    audio_data: bytes
    duration_sec: float
    format: str
    engine: str
    voice_id: str
    segment_count: int
    total_chars: int


class TTSService:
    """TTS 合成服务。

    流程：
    1. 文本分段
    2. 逐段合成
    3. 音频拼接
    """

    def __init__(
        self,
        engine: TTSEngine | None = None,
        segmenter: TextSegmenter | None = None,
    ) -> None:
        self._engine = engine
        self._segmenter = segmenter or TextSegmenter()

    async def synthesize_article(
        self,
        text: str,
        voice_id: str | None = None,
        speed: float = 1.0,
    ) -> AudioOutput:
        """将长文章合成为完整音频。

        Args:
            text: 文章全文（Markdown 格式）
            voice_id: 音色 ID
            speed: 语速

        Returns:
            完整音频输出
        """
        if self._engine is None:
            self._engine = create_tts_engine()

        # 1. 分段
        segments = self._segmenter.segment(text)
        if not segments:
            raise TTSError("文本为空，无法合成", error_num=9)

        logger.info(
            "tts_synthesis_starting",
            segments=len(segments),
            total_chars=sum(s.char_count for s in segments),
            engine=self._engine.name,
        )

        # 2. 逐段合成
        audio_chunks: list[bytes] = []
        total_duration = 0.0
        last_voice = voice_id or ""

        for seg in segments:
            try:
                result: SynthesisResult = await self._engine.synthesize(
                    text=seg.text,
                    voice_id=voice_id,
                    speed=speed,
                )
                audio_chunks.append(result.audio_data)
                total_duration += result.duration_sec
                last_voice = result.voice_id
            except TTSError as e:
                logger.error(
                    "tts_segment_failed",
                    segment_index=seg.index,
                    error=str(e),
                )
                # 用静音填充失败段落，不中断整体
                silence = self._generate_silence(2.0, 16000)
                audio_chunks.append(silence)
                total_duration += 2.0

        # 3. 拼接音频
        combined = self._concat_mp3(audio_chunks)

        output = AudioOutput(
            audio_data=combined,
            duration_sec=round(total_duration, 2),
            format="mp3",
            engine=self._engine.name,
            voice_id=last_voice,
            segment_count=len(segments),
            total_chars=sum(s.char_count for s in segments),
        )

        logger.info(
            "tts_synthesis_complete",
            duration=output.duration_sec,
            size=len(output.audio_data),
            segments=output.segment_count,
        )
        return output

    async def close(self) -> None:
        """释放资源。"""
        if self._engine:
            await self._engine.close()

    def _concat_mp3(self, chunks: list[bytes]) -> bytes:
        """拼接 MP3 音频块。

        MP3 是流式格式，直接拼接即可（无需重新编码）。
        """
        return b"".join(chunks)

    def _generate_silence(self, duration_sec: float, sample_rate: int) -> bytes:
        """生成静音 WAV 数据（用于失败段落填充）。"""
        num_samples = int(duration_sec * sample_rate)
        # 简单的 WAV 头 + 静音数据
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            36 + num_samples * 2,
            b"WAVE",
            b"fmt ",
            16,
            1,  # PCM
            1,  # mono
            sample_rate,
            sample_rate * 2,
            2,
            16,
            b"data",
            num_samples * 2,
        )
        silence_data = b"\x00" * (num_samples * 2)
        return header + silence_data
