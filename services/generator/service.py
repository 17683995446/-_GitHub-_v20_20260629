"""文档生成服务：整合 Repomix + LLM + Prompt，生成通俗解读文章。"""

from __future__ import annotations

from dataclasses import dataclass

from services.generator.llm_client import LLMClient, LLMResponse
from services.generator.prompt_manager import PromptManager, get_prompt_manager
from services.generator.repomix_client import RepomixClient
from shared.config import get_settings
from shared.errors import GeneratorError
from shared.logging import get_logger

logger = get_logger(__name__)

# 文章长度档位（决策 Q6：按项目规模自适应）
WORD_LIMITS = {
    "small": {"min_words": 1500, "max_words": 2500},
    "medium": {"min_words": 2000, "max_words": 3000},
    "large": {"min_words": 2500, "max_words": 4000},
}


@dataclass
class GeneratedArticle:
    """生成的文章结构。"""

    title: str
    body_md: str
    word_count: int
    llm_model: str
    prompt_version: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class GeneratorService:
    """文档生成服务。

    流程：
    1. 获取仓库 README 摘录
    2. 加载 Prompt 模板
    3. 调用 LLM 生成文章
    4. 后处理（字数统计、标题提取）
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        repomix_client: RepomixClient | None = None,
        prompt_manager: PromptManager | None = None,
    ) -> None:
        self._llm = llm_client
        self._repomix = repomix_client or RepomixClient()
        self._prompt_manager = prompt_manager or get_prompt_manager()
        self._settings = get_settings()

    async def generate(
        self,
        repo_name: str,
        repo_full_name: str,
        repo_description: str,
        repo_language: str,
        repo_stars: int,
        repo_license: str,
        repo_url: str,
        readme_excerpt: str | None = None,
        project_size: str = "medium",
    ) -> GeneratedArticle:
        """生成一篇通俗解读文章。

        Args:
            repo_name: 仓库名称
            repo_full_name: 全名（owner/repo）
            repo_description: 项目描述
            repo_language: 主语言
            repo_stars: Star 数
            repo_license: 许可证
            repo_url: 仓库 URL
            readme_excerpt: README 摘录（如已有则不重复获取）
            project_size: 项目规模 small/medium/large

        Returns:
            GeneratedArticle 结构
        """
        if project_size not in WORD_LIMITS:
            raise GeneratorError(
                f"无效的 project_size: {project_size}",
                error_num=8,
            )

        # 1. 获取 README 摘录
        if not readme_excerpt:
            try:
                readme_excerpt = await self._repomix.get_readme_excerpt(repo_url)
            except Exception as e:
                logger.warning("readme_fetch_failed", repo=repo_full_name, error=str(e))
                readme_excerpt = repo_description or "（无 README）"

        # 2. 加载 Prompt 模板
        template = self._prompt_manager.load("project-interpret", version="latest")
        word_limits = WORD_LIMITS[project_size]

        # 3. 渲染 Prompt
        user_prompt = template.render(
            repo_name=repo_name,
            repo_full_name=repo_full_name,
            repo_description=repo_description or "暂无描述",
            repo_language=repo_language or "未指定",
            repo_stars=repo_stars,
            repo_license=repo_license or "未指定",
            readme_excerpt=readme_excerpt[:3000],
            code_structure="（代码结构详情见 README）",
            min_words=word_limits["min_words"],
            max_words=word_limits["max_words"],
        )

        # 4. 调用 LLM
        if self._llm is None:
            self._llm = LLMClient()

        messages = [
            {
                "role": "system",
                "content": "你是一位资深技术科普作者，擅长用通俗易懂的中文解读开源项目。",
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info(
            "article_generating",
            repo=repo_full_name,
            prompt_version=template.version,
            estimated_tokens=template.metadata.get("expected_output_tokens", 3000),
        )

        response: LLMResponse = await self._llm.chat(
            messages=messages,
            max_tokens=word_limits["max_words"] * 2,  # token 约为字数 1.5-2 倍
        )

        # 5. 后处理
        title = self._extract_title(response.content)
        word_count = self._count_words(response.content)

        article = GeneratedArticle(
            title=title,
            body_md=response.content,
            word_count=word_count,
            llm_model=response.model,
            prompt_version=template.version,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
        )

        logger.info(
            "article_generated",
            repo=repo_full_name,
            title=title,
            word_count=word_count,
            total_tokens=response.total_tokens,
        )
        return article

    async def close(self) -> None:
        """释放资源。"""
        if self._llm:
            await self._llm.close()

    def _extract_title(self, content: str) -> str:
        """从 Markdown 内容中提取标题。"""
        lines = content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("# ") and not line.startswith("## "):
                return line.lstrip("# ").strip()
            if line.startswith("## ") and "价值主张" in line:
                # 找下一行
                idx = lines.index(line)
                if idx + 1 < len(lines):
                    return lines[idx + 1].strip()
        # 没找到标题，取前 50 字
        return content.strip()[:50]

    def _count_words(self, content: str) -> int:
        """统计中文字数。"""
        # 移除 Markdown 标记
        import re

        clean = re.sub(r"[#*`\-|>]", "", content)
        # 中文字符 + 英文单词
        chinese_chars = sum(1 for c in clean if "\u4e00" <= c <= "\u9fff")
        english_words = len(re.findall(r"[a-zA-Z]+", clean))
        return chinese_chars + english_words
