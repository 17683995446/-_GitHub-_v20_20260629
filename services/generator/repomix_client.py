"""Repomix 集成：将 GitHub 仓库打包为 AI 友好文本。

遵循"站在巨人肩膀上"原则：不自己解析仓库，调用 Repomix CLI。
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass

from shared.errors import ExternalError
from shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RepoPackResult:
    """仓库打包结果。"""

    repo_url: str
    content: str
    token_count: int
    file_count: int


class RepomixClient:
    """Repomix CLI 封装。

    使用 `npx repomix --remote <url> --compress` 将仓库打包。
    需要系统已安装 Node.js（npx）。
    """

    def __init__(self) -> None:
        self._npx_available: bool | None = None

    async def _check_npx(self) -> bool:
        """检查 npx 是否可用。"""
        if self._npx_available is not None:
            return self._npx_available
        self._npx_available = shutil.which("npx") is not None
        if not self._npx_available:
            logger.warning("npx_not_found", msg="Repomix 需要 Node.js 环境")
        return self._npx_available

    async def pack_repository(
        self,
        repo_url: str,
        compress: bool = True,
        include_logs: bool = False,
        max_file_size: str = "500kb",
    ) -> RepoPackResult:
        """将远程仓库打包为 AI 友好文本。

        Args:
            repo_url: GitHub 仓库 URL
            compress: 是否用 Tree-sitter 压缩代码
            include_logs: 是否包含 commit 日志
            max_file_size: 单文件大小限制

        Returns:
            打包结果
        """
        if not await self._check_npx():
            raise ExternalError(
                "npx 未安装，无法使用 Repomix。请先安装 Node.js。",
                code="20004",
            )

        # 构建 npx repomix 命令
        cmd = [
            "npx",
            "repomix",
            "--remote",
            repo_url,
            "--style",
            "markdown",
            "--output",
            "-",  # 输出到 stdout
            "--no-file-summary",
        ]
        if compress:
            cmd.append("--compress")
        if include_logs:
            cmd.extend(["--include-diffs"])
        cmd.extend(["--max-file-size", max_file_size])

        logger.info("repomix_packing", repo=repo_url, compress=compress)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=120
            )
        except asyncio.TimeoutError as e:
            raise ExternalError(
                f"Repomix 打包超时（120s）: {repo_url}",
                code="20005",
            ) from e
        except Exception as e:
            raise ExternalError(
                f"Repomix 执行失败: {e}",
                code="20006",
            ) from e

        if proc.returncode != 0:
            error_msg = stderr_bytes.decode("utf-8", errors="replace")[:500]
            raise ExternalError(
                f"Repomix 打包失败: {error_msg}",
                code="20007",
            )

        content = stdout_bytes.decode("utf-8", errors="replace")
        token_count = self._estimate_tokens(content)

        result = RepoPackResult(
            repo_url=repo_url,
            content=content,
            token_count=token_count,
            file_count=content.count("## File:"),
        )

        logger.info(
            "repomix_packed",
            repo=repo_url,
            token_count=token_count,
            file_count=result.file_count,
            content_length=len(content),
        )
        return result

    def _estimate_tokens(self, text: str) -> int:
        """粗略估算 token 数（中文约 1 字 = 1.5 token，英文约 4 字符 = 1 token）。"""
        chinese_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        other_chars = len(text) - chinese_count
        return int(chinese_count * 1.5 + other_chars / 4)

    async def get_readme_excerpt(self, repo_url: str, max_length: int = 3000) -> str:
        """获取仓库 README 的摘录（轻量级，不打包整个仓库）。

        当只需要 README 时，用这个方法比 pack_repository 更快。
        """
        # 从 repo_url 提取 owner/repo
        # https://github.com/owner/repo -> owner/repo
        parts = repo_url.rstrip("/").split("/")
        if len(parts) < 2:
            raise ExternalError(f"无效的仓库 URL: {repo_url}", code="20008")

        owner_repo = "/".join(parts[-2:])

        # 使用 GitHub raw README
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            # 尝试多种 README 文件名
            for readme_path in ["README.md", "readme.md", "README.rst", "README"]:
                url = f"https://raw.githubusercontent.com/{owner_repo}/HEAD/{readme_path}"
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        content = resp.text[:max_length]
                        logger.info(
                            "readme_fetched",
                            repo=owner_repo,
                            length=len(content),
                        )
                        return content
                except httpx.RequestError:
                    continue

        raise ExternalError(
            f"无法获取 README: {owner_repo}",
            code="20009",
        )
