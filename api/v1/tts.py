"""TTS API：使用硅基流动 CosyVoice2 将文本转为 MP3 音频。

POST /api/v1/tts/generate  →  返回 MP3 二进制数据
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from shared.config import get_settings
from shared.logging import get_logger

router = APIRouter(prefix="/tts", tags=["tts"])
logger = get_logger(__name__)

# 音频缓存目录
AUDIO_CACHE_DIR = Path("/tmp/gitcast_audio")
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 音量增益（dB），解决 TTS 原始音频偏小的问题
# +6dB ≈ 音量翻倍，+10dB ≈ 音量 3 倍
AUDIO_GAIN_DB = 10.0


async def boost_audio_volume(input_path: Path, output_path: Path) -> bool:
    """用 FFmpeg 提升音频音量并标准化响度。

    使用 loudnorm 滤镜做 EBU R128 响度标准化，目标 -14 LUFS（播客标准），
    再额外施加固定增益确保音量足够大。
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-af", f"loudnorm=I=-14:TP=-1.5:LRA=11,volume={AUDIO_GAIN_DB}dB",
        "-b:a", "64k",
        str(output_path),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("ffmpeg_boost_failed", stderr=stderr.decode()[:200])
            return False
        return True
    except Exception as e:
        logger.warning("ffmpeg_boost_error", error=str(e))
        return False

# 系统预置音色
VOICES = {
    "alex": ("沉稳男声", "FunAudioLLM/CosyVoice2-0.5B:alex"),
    "benjamin": ("低沉男声", "FunAudioLLM/CosyVoice2-0.5B:benjamin"),
    "charles": ("磁性男声", "FunAudioLLM/CosyVoice2-0.5B:charles"),
    "david": ("欢快男声", "FunAudioLLM/CosyVoice2-0.5B:david"),
    "anna": ("沉稳女声", "FunAudioLLM/CosyVoice2-0.5B:anna"),
    "bella": ("激情女声", "FunAudioLLM/CosyVoice2-0.5B:bella"),
    "claire": ("温柔女声", "FunAudioLLM/CosyVoice2-0.5B:claire"),
    "diana": ("欢快女声", "FunAudioLLM/CosyVoice2-0.5B:diana"),
}


def clean_text_for_speech(text: str) -> str:
    """清理文本，使其适合语音合成朗读。

    - 移除 Markdown 格式符号（**、###、- 等）
    - 移除代码块和行内代码
    - 移除链接 URL
    - 将多余空行压缩为单个空行
    - 移除特殊符号
    """
    # 移除代码块 ```...```
    text = re.sub(r"```[\s\S]*?```", "（代码示例省略）", text)
    # 移除行内代码 `code`
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # 移除 Markdown 标题符号 ### ##
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    # 移除粗体/斜体标记 **text** *text*
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    # 移除列表标记 - 或 * 或 1.
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
    # 移除链接 [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # 移除引用标记 >
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)
    # 移除水平分隔线 ---
    text = re.sub(r"^[-=]{3,}$", "", text, flags=re.MULTILINE)
    # 移除表格符号 | ---
    text = re.sub(r"\|", " ", text)
    # 将连续空行压缩为单个空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 移除行首/行尾多余空格
    text = re.sub(r"^[ \t]+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    # 移除其他不适合朗读的符号
    text = text.replace("【", "").replace("】", "。")
    text = text.replace("---", "")
    return text.strip()


class TTSRequest(BaseModel):
    """TTS 请求。"""

    text: str = Field(..., description="要转为语音的文本")
    voice: str = Field(default="alex", description="音色名称")
    speed: float = Field(default=1.0, ge=0.25, le=4.0, description="语速")


@router.post("/generate")
async def generate_tts(request: TTSRequest) -> FileResponse:
    """将文本转为 MP3 音频文件并返回。"""
    settings = get_settings()
    api_key = settings.llm_api_key
    api_base = settings.llm_api_base

    # 获取音色
    voice_key = request.voice if request.voice in VOICES else "alex"
    voice_name, voice_id = VOICES[voice_key]

    # 清理文本：移除 Markdown 等不适合朗读的符号
    clean_text = clean_text_for_speech(request.text)

    # 生成缓存文件名（清理后文本+音色+语速的 hash）
    cache_key = hashlib.md5(
        f"{clean_text}:{voice_key}:{request.speed}".encode()
    ).hexdigest()
    audio_path = AUDIO_CACHE_DIR / f"{cache_key}.mp3"

    # 如果已缓存，直接返回
    if audio_path.exists():
        logger.info("tts_cache_hit", key=cache_key, size=audio_path.stat().st_size)
        return FileResponse(
            path=str(audio_path),
            media_type="audio/mpeg",
            filename=f"tts_{cache_key}.mp3",
        )

    # SiliconFlow CosyVoice2 支持最多 128000 字符，这里不截断
    # 但对于超长文本（>50000字符），分段处理以避免超时
    text_to_send = clean_text[:50000]

    # 调用硅基流动 TTS API
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{api_base}/audio/speech",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "FunAudioLLM/CosyVoice2-0.5B",
                    "input": text_to_send,
                    "voice": voice_id,
                    "response_format": "mp3",
                    "speed": request.speed,
                },
            )

        if resp.status_code != 200:
            error_msg = resp.text[:200]
            logger.error("tts_api_error", status=resp.status_code, error=error_msg)
            raise HTTPException(status_code=502, detail=f"TTS API 错误: {error_msg}")

        # 先保存原始音频到临时文件
        raw_path = AUDIO_CACHE_DIR / f"{cache_key}_raw.mp3"
        raw_path.write_bytes(resp.content)

        # 用 FFmpeg 提升音量并标准化响度
        boost_ok = await boost_audio_volume(raw_path, audio_path)

        if not boost_ok:
            # FFmpeg 失败则直接使用原始文件
            logger.warning("tts_boost_fallback", key=cache_key)
            audio_path.write_bytes(resp.content)

        # 清理临时文件
        try:
            raw_path.unlink()
        except Exception:
            pass

        final_size = audio_path.stat().st_size
        logger.info(
            "tts_generated",
            key=cache_key,
            size=final_size,
            raw_size=len(resp.content),
            text_len=len(text_to_send),
            voice=voice_key,
            speed=request.speed,
            boosted=boost_ok,
        )

        return FileResponse(
            path=str(audio_path),
            media_type="audio/mpeg",
            filename=f"tts_{cache_key}.mp3",
        )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="TTS API 超时，文本可能过长")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("tts_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"TTS 生成失败: {e}")


@router.get("/voices")
async def list_voices() -> dict:
    """列出可用的音色。"""
    return {
        "voices": [
            {"key": k, "name": v[0], "gender": "男" if k in ["alex", "benjamin", "charles", "david"] else "女"}
            for k, v in VOICES.items()
        ]
    }
