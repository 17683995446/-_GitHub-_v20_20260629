"""Prompt 模板管理器。

遵循代码规范 3.4：Prompt 独立目录、SemVer 版本管理。
Prompt 文件存放于 /prompts/<task>/<version>.md
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from shared.errors import GeneratorError
from shared.logging import get_logger

logger = get_logger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


class PromptTemplate:
    """Prompt 模板实例。"""

    def __init__(self, name: str, version: str, content: str, metadata: dict[str, Any]) -> None:
        self.name = name
        self.version = version
        self.content = content
        self.metadata = metadata

    def render(self, **variables: Any) -> str:
        """渲染模板，替换 {{variable}} 占位符。

        Args:
            **variables: 模板变量

        Returns:
            渲染后的 Prompt 字符串

        Raises:
            GeneratorError: 有未替换的变量
        """
        rendered = self.content
        for key, value in variables.items():
            placeholder = "{{" + key + "}}"
            rendered = rendered.replace(placeholder, str(value))

        # 检查是否有未替换的变量
        remaining = re.findall(r"\{\{(\w+)\}\}", rendered)
        if remaining:
            raise GeneratorError(
                f"Prompt 模板有未替换的变量: {remaining}",
                error_num=3,
            )

        return rendered


class PromptManager:
    """Prompt 模板管理器。

    从文件系统加载 Prompt，支持版本管理。
    """

    def __init__(self, prompts_dir: Path | None = None) -> None:
        self._prompts_dir = prompts_dir or PROMPTS_DIR
        self._cache: dict[str, PromptTemplate] = {}

    def load(self, name: str, version: str = "latest") -> PromptTemplate:
        """加载指定版本的 Prompt 模板。

        Args:
            name: Prompt 名称（对应目录名）
            version: 版本号，"latest" 表示最新版本

        Returns:
            PromptTemplate 实例
        """
        cache_key = f"{name}:{version}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt_dir = self._prompts_dir / name
        if not prompt_dir.exists():
            raise GeneratorError(
                f"Prompt 目录不存在: {prompt_dir}",
                error_num=4,
            )

        if version == "latest":
            # 找最新版本
            versions = sorted(
                [f.stem for f in prompt_dir.glob("*.md")],
                reverse=True,
            )
            if not versions:
                raise GeneratorError(
                    f"Prompt 目录无模板文件: {prompt_dir}",
                    error_num=5,
                )
            version = versions[0]

        prompt_file = prompt_dir / f"{version}.md"
        if not prompt_file.exists():
            raise GeneratorError(
                f"Prompt 文件不存在: {prompt_file}",
                error_num=6,
            )

        content = prompt_file.read_text(encoding="utf-8")
        metadata, body = self._parse_frontmatter(content)

        template = PromptTemplate(
            name=name,
            version=version,
            content=body,
            metadata=metadata,
        )
        self._cache[cache_key] = template
        logger.info("prompt_loaded", name=name, version=version)
        return template

    def _parse_frontmatter(self, content: str) -> tuple[dict[str, Any], str]:
        """解析 YAML frontmatter。

        格式：
        ---
        key: value
        ---
        # Prompt body...
        """
        if not content.startswith("---"):
            return {}, content

        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}, content

        try:
            metadata = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError as e:
            raise GeneratorError(
                f"Prompt frontmatter 解析失败: {e}",
                error_num=7,
            ) from e

        body = parts[2].strip()
        return metadata, body


# 全局单例
_prompt_manager: PromptManager | None = None


def get_prompt_manager() -> PromptManager:
    """获取全局 Prompt 管理器单例。"""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager
