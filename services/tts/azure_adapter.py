"""Azure TTS 适配器。

通过 Azure Cognitive Services Speech API 合成音频。
遵循架构规范 2.2：可替换，改配置不改代码。
"""

from __future__ import annotations

import httpx

from services.tts.base import SynthesisResult, TTSEngine
from shared.config import get_settings
from shared.errors import TTSError
from shared.logging import get_logger

logger = get_logger(__name__)

# Azure TTS 端点模板
AZURE_TTS_URL = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"


class AzureTTSAdapter(TTSEngine):
    """Azure Cognitive Services TTS 适配器。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._key = self._settings.azure_speech_key
        self._region = self._settings.azure_speech_region
        if not self._key:
            raise TTSError("Azure Speech Key 未配置", error_num=1)
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "azure"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Ocp-Apim-Subscription-Key": self._key,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
                    "User-Agent": "GitCast/0.1",
                },
                timeout=60.0,
            )
        return self._client

    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        speed: float = 1.0,
    ) -> SynthesisResult:
        """通过 Azure TTS 合成音频。"""
        voice = voice_id or self._settings.tts_voice
        client = await self._get_client()
        url = AZURE_TTS_URL.format(region=self._region)

        # 构建 SSML
        speed_percent = int(speed * 100)
        ssml = (
            "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
            f"xml:lang='zh-CN'>"
            f"<voice name='{voice}'>"
            f"<prosody rate='{speed_percent}%'>"
            f"{self._escape_xml(text)}"
            f"</prosody>"
            f"</voice>"
            f"</speak>"
        )

        logger.debug("azure_tts_request", voice=voice, text_length=len(text))

        try:
            resp = await client.post(url, content=ssml)
        except httpx.RequestError as e:
            raise TTSError(f"Azure TTS 请求失败: {e}", error_num=2) from e

        if resp.status_code == 401:
            raise TTSError("Azure Speech Key 无效", error_num=3)
        if resp.status_code == 429:
            raise TTSError("Azure TTS 限流", error_num=4)
        if resp.status_code != 200:
            raise TTSError(
                f"Azure TTS 异常: {resp.status_code}",
                error_num=5,
            )

        audio_data = resp.content
        duration_sec = self._estimate_duration(len(audio_data), len(text))

        result = SynthesisResult(
            audio_data=audio_data,
            duration_sec=duration_sec,
            sample_rate=16000,
            format="mp3",
            engine=self.name,
            voice_id=voice,
        )

        logger.info(
            "azure_tts_synthesized",
            voice=voice,
            duration=duration_sec,
            size=len(audio_data),
        )
        return result

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _escape_xml(self, text: str) -> str:
        """转义 XML 特殊字符。"""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    def _estimate_duration(self, audio_size: int, text_length: int) -> float:
        """估算音频时长。

        MP3 128kbps: 16KB/s
        或按文本：中文约 4 字/秒
        """
        if audio_size > 0:
            return audio_size / 16000  # 128kbps = 16KB/s
        return text_length / 4.0  # 备选估算
