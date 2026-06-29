"""Prompt 管理器单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.generator.prompt_manager import PromptManager, PromptTemplate


class TestPromptTemplate:
    """Prompt 模板渲染测试。"""

    def test_render_replaces_variables(self) -> None:
        """变量替换测试。"""
        template = PromptTemplate(
            name="test",
            version="1.0.0",
            content="Hello {{name}}, your repo is {{repo}}.",
            metadata={},
        )
        result = template.render(name="World", repo="langchain")
        assert result == "Hello World, your repo is langchain."

    def test_render_missing_variable_raises(self) -> None:
        """未替换变量应报错。"""
        template = PromptTemplate(
            name="test",
            version="1.0.0",
            content="Hello {{name}}, {{missing}} is not set.",
            metadata={},
        )
        with pytest.raises(Exception, match="未替换"):
            template.render(name="World")

    def test_render_no_variables(self) -> None:
        """无变量模板应原样返回。"""
        template = PromptTemplate(
            name="test",
            version="1.0.0",
            content="Static content with no placeholders.",
            metadata={},
        )
        result = template.render()
        assert result == "Static content with no placeholders."


class TestPromptManager:
    """Prompt 管理器测试。"""

    @pytest.fixture
    def temp_prompts_dir(self, tmp_path: Path) -> Path:
        """创建临时 Prompt 目录。"""
        prompt_dir = tmp_path / "test-prompt"
        prompt_dir.mkdir()
        prompt_content = """---
name: test-prompt
version: 0.1.0
owner: test
---

# Role
You are a {{role}}.

# Task
Analyze {{project}}.
"""
        (prompt_dir / "0.1.0.md").write_text(prompt_content, encoding="utf-8")

        # 创建更新版本
        prompt_v2 = prompt_content.replace("0.1.0", "0.2.0")
        (prompt_dir / "0.2.0.md").write_text(prompt_v2, encoding="utf-8")

        return tmp_path

    def test_load_specific_version(self, temp_prompts_dir: Path) -> None:
        """加载指定版本。"""
        manager = PromptManager(prompts_dir=temp_prompts_dir)
        template = manager.load("test-prompt", version="0.1.0")
        assert template.version == "0.1.0"
        assert "test-prompt" in template.name or "test" in template.name

    def test_load_latest_version(self, temp_prompts_dir: Path) -> None:
        """latest 应加载最新版本。"""
        manager = PromptManager(prompts_dir=temp_prompts_dir)
        template = manager.load("test-prompt", version="latest")
        assert template.version == "0.2.0"

    def test_load_caches(self, temp_prompts_dir: Path) -> None:
        """重复加载应命中缓存。"""
        manager = PromptManager(prompts_dir=temp_prompts_dir)
        t1 = manager.load("test-prompt", version="0.1.0")
        t2 = manager.load("test-prompt", version="0.1.0")
        assert t1 is t2

    def test_load_nonexistent_dir(self, tmp_path: Path) -> None:
        """不存在的目录应报错。"""
        manager = PromptManager(prompts_dir=tmp_path)
        with pytest.raises(Exception, match="目录不存在"):
            manager.load("nonexistent")

    def test_frontmatter_parsed(self, temp_prompts_dir: Path) -> None:
        """frontmatter 应正确解析为 metadata。"""
        manager = PromptManager(prompts_dir=temp_prompts_dir)
        template = manager.load("test-prompt", version="0.1.0")
        assert template.metadata["name"] == "test-prompt"
        assert template.metadata["version"] == "0.1.0"
        assert template.metadata["owner"] == "test"

    def test_render_with_variables(self, temp_prompts_dir: Path) -> None:
        """加载后渲染应替换变量。"""
        manager = PromptManager(prompts_dir=temp_prompts_dir)
        template = manager.load("test-prompt", version="0.1.0")
        result = template.render(role="scientist", project="LangChain")
        assert "scientist" in result
        assert "LangChain" in result
        assert "{{" not in result
