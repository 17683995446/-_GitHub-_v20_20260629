"""文本分段器：将长文章切分为适合 TTS 处理的小段。

遵循代码规范：长文本需分段拼接，避免音色漂移与韵律断裂。
分段策略：按段落 → 按句子 → 控制最大长度。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shared.logging import get_logger

logger = get_logger(__name__)

# 每段最大字符数（中文约 500 字 ≈ 2 分钟音频）
MAX_SEGMENT_CHARS = 800
# 每段最小字符数（避免过短段落）
MIN_SEGMENT_CHARS = 50


@dataclass
class TextSegment:
    """文本分段。"""

    index: int
    text: str
    char_count: int


class TextSegmenter:
    """文本分段器。

    分段策略（按优先级）：
    1. 按段落分割（双换行）
    2. 段落过长则按句子分割（。！？.!?）
    3. 合并过短段落
    """

    def segment(self, text: str) -> list[TextSegment]:
        """将长文本分段。

        Args:
            text: 原始文本（可能含 Markdown 标记）

        Returns:
            分段列表
        """
        # 1. 清理 Markdown 标记
        clean_text = self._strip_markdown(text)

        # 2. 按段落分割
        paragraphs = self._split_paragraphs(clean_text)

        # 3. 段落过长则按句子分割
        segments: list[str] = []
        for para in paragraphs:
            if len(para) > MAX_SEGMENT_CHARS:
                sentences = self._split_sentences(para)
                segments.extend(self._merge_short_sentences(sentences))
            else:
                segments.append(para)

        # 4. 合并过短段落
        segments = self._merge_short_segments(segments)

        # 5. 构建结果
        result = [
            TextSegment(
                index=i,
                text=s.strip(),
                char_count=len(s.strip()),
            )
            for i, s in enumerate(segments)
            if s.strip()
        ]

        logger.info(
            "text_segmented",
            input_length=len(text),
            segment_count=len(result),
            avg_length=(sum(r.char_count for r in result) / len(result) if result else 0),
        )
        return result

    def _strip_markdown(self, text: str) -> str:
        """移除 Markdown 格式标记，保留纯文本。"""
        # 移除标题标记
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # 移除粗体/斜体
        text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
        # 移除代码块
        text = re.sub(r"```[\s\S]*?```", "（代码块）", text)
        # 移除行内代码
        text = re.sub(r"`(.+?)`", r"\1", text)
        # 移除链接，保留文字
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # 移除图片
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", "", text)
        # 移除列表标记
        text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
        # 移除引用标记
        text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)
        # 移除水平线
        text = re.sub(r"^---+$", "", text, flags=re.MULTILINE)
        return text.strip()

    def _split_paragraphs(self, text: str) -> list[str]:
        """按双换行分割段落。"""
        paras = re.split(r"\n\s*\n", text)
        return [p.strip() for p in paras if p.strip()]

    def _split_sentences(self, text: str) -> list[str]:
        """按句子分割（中英文标点）。"""
        # 中英文句子结束标记
        sentences = re.split(r"(?<=[。！？.!?；;])\s*", text)
        return [s.strip() for s in sentences if s.strip()]

    def _merge_short_sentences(self, sentences: list[str]) -> list[str]:
        """合并过短句子。"""
        merged: list[str] = []
        buffer = ""

        for sent in sentences:
            if len(buffer) + len(sent) > MAX_SEGMENT_CHARS:
                if buffer:
                    merged.append(buffer)
                    buffer = sent
                else:
                    merged.append(sent)
            else:
                buffer = buffer + sent if buffer else sent

        if buffer:
            merged.append(buffer)
        return merged

    def _merge_short_segments(self, segments: list[str]) -> list[str]:
        """合并过短的段落。"""
        if not segments:
            return []

        merged: list[str] = []
        buffer = ""

        for seg in segments:
            if len(buffer) + len(seg) + 1 > MAX_SEGMENT_CHARS:
                if buffer:
                    merged.append(buffer)
                    buffer = seg
                else:
                    merged.append(seg)
            elif len(seg) < MIN_SEGMENT_CHARS:
                buffer = buffer + " " + seg if buffer else seg
            else:
                if buffer:
                    merged.append(buffer + " " + seg)
                    buffer = ""
                else:
                    merged.append(seg)

        if buffer:
            merged.append(buffer)
        return merged
