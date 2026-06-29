"""CosyVoice2 适配器（自托管）。

通过 CosyVoice2 的 HTTP API 合成音频。
Apache-2.0 许可证，可商用。
"""

from __future__ import annotations

import httpx

from services.tts.base import SynthesisResult, TTSEngine
from shared.config import get_settings
from shared.errors import TTSError
from shared.logging import get_logger

logger = get_logger(__name__)


class CosyVoiceAdapter(TTSEngine):
    """CosyVoice2 自托管 TTS 适配器。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._api_base = self._settings.cosyvoice_api_base
        self._default_voice = self._settings.cosyvoice_default_voice
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "cosyvoice"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._api_base,
                timeout=120.0,
            )
        return self._client

    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        speed: float = 1.0,
    ) -> SynthesisResult:
        """通过 CosyVoice2 API 合成音频。

        CosyVoice2 API 接口（兼容 OpenAI TTS 格式）：
        POST /v1/audio/speech
        {
            "model": "cosyvoice-v2",
            "input": "text",
            "voice": "voice_id",
            "response_format": "mp3",
            "speed": 1.0
        }
        """
        voice = voice_id or self._default_voice
        client = await self._get_client()

        payload = {
            "model": "cosyvoice-v2",
            "input": text,
            "voice": voice,
            "response_format": "mp3",
            "speed": speed,
        }

        logger.debug(
            "cosyvoice_tts_request",
            voice=voice,
            text_length=len(text),
        )

        try:
            resp = await client.post("/v1/audio/speech", json=payload)
        except httpx.RequestError as e:
            raise TTSError(
                f"CosyVoice 请求失败: {e}",
                error_num=6,
            ) from e

        if resp.status_code != 200:
            error_msg = resp.text[:200] if resp.text else "unknown"
            raise TTSError(
                f"CosyVoice 异常: {resp.status_code} {error_msg}",
                error_num=7,
            )

        audio_data = resp.content
        duration_sec = self._estimate_duration(len(audio_data), len(text))

        result = SynthesisResult(
            audio_data=audio_data,
            duration_sec=duration_sec,
            sample_rate=24000,
            format="mp3",
            engine=self.name,
            voice_id=voice,
        )

        logger.info(
            "cosyvoice_tts_synthesized",
            voice=voice,
            duration=duration_sec,
            size=len(audio_data),
        )
        return result

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _estimate_duration(self, audio_size: int, text_length: int) -> float:
        """估算音频时长。CosyVoice2 输出 24kHz MP3。"""
        if audio_size > 0:
            # 24kHz mono 16-bit ≈ 48KB/s，MP3 压缩约 1/4 ≈ 12KB/s
            return audio_size / 12000
        return text_length / 4.0
