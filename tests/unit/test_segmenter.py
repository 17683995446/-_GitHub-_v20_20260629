"""文本分段器单元测试。"""

from __future__ import annotations

from services.tts.segmenter import TextSegmenter


class TestTextSegmenter:
    """文本分段器测试。"""

    def setup_method(self) -> None:
        self.segmenter = TextSegmenter()

    def test_short_text_single_segment(self) -> None:
        """短文本应为单段。"""
        text = "这是一段短文本。"
        segments = self.segmenter.segment(text)
        assert len(segments) == 1
        assert segments[0].text == "这是一段短文本。"

    def test_long_text_multiple_segments(self) -> None:
        """长文本应分段。"""
        para = "这是一个很长的段落。" * 100
        text = para + "\n\n" + "第二段内容。" * 100
        segments = self.segmenter.segment(text)
        assert len(segments) > 1
        for seg in segments:
            assert len(seg.text) <= 800 + 50  # 允许少量溢出

    def test_markdown_stripped(self) -> None:
        """Markdown 标记应被移除。"""
        text = "## 标题\n\n**粗体**内容`代码`[链接](url)\n\n- 列表项"
        segments = self.segmenter.segment(text)
        combined = " ".join(s.text for s in segments)
        assert "##" not in combined
        assert "**" not in combined
        assert "`" not in combined
        assert "[" not in combined

    def test_paragraph_split(self) -> None:
        """段落应按双换行分割（每段需超过 MIN_SEGMENT_CHARS 以避免合并）。"""
        para1 = "第一段内容。" * 10  # 60 chars, above MIN_SEGMENT_CHARS=50
        para2 = "第二段内容。" * 10
        para3 = "第三段内容。" * 10
        text = f"{para1}\n\n{para2}\n\n{para3}"
        segments = self.segmenter.segment(text)
        texts = [s.text for s in segments]
        assert len(segments) == 3
        assert para1 in texts
        assert para2 in texts
        assert para3 in texts

    def test_sentence_split_for_long_paragraph(self) -> None:
        """长段落应按句子分割。"""
        sentences = "这是一个句子。" * 200
        text = sentences  # 单段落但很长
        segments = self.segmenter.segment(text)
        assert len(segments) > 1

    def test_empty_text(self) -> None:
        """空文本应返回空列表。"""
        segments = self.segmenter.segment("")
        assert segments == []

    def test_segment_index_sequential(self) -> None:
        """分段索引应连续递增。"""
        text = "段落一。\n\n段落二。\n\n段落三。"
        segments = self.segmenter.segment(text)
        for i, seg in enumerate(segments):
            assert seg.index == i

    def test_min_segment_length(self) -> None:
        """合并后段落不应过短。"""
        text = "短。\n\n短。\n\n短。\n\n这是一个正常长度的段落内容。"
        segments = self.segmenter.segment(text)
        for seg in segments:
            assert len(seg.text) >= 5  # 至少不会是单字

    def test_code_block_replaced(self) -> None:
        """代码块应被替换为占位符。"""
        text = "正文内容。\n\n```python\nprint('hello')\n```\n\n后续内容。"
        segments = self.segmenter.segment(text)
        combined = " ".join(s.text for s in segments)
        assert "print" not in combined or "代码块" in combined
