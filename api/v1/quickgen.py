"""快速生成 API：不依赖数据库，异步发现项目+生成文章。

使用后台任务模式避免网关超时：
  POST /run  → 立即返回 job_id
  GET  /status/{job_id} → 轮询任务状态（支持实时进度+流式结果）

支持大批量生成（最高1000篇），通过 GitHub Search API 分页获取项目。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from shared.config import get_settings
from shared.logging import get_logger

router = APIRouter(prefix="/quickgen", tags=["quickgen"])
logger = get_logger(__name__)

# ===== 内存任务存储 =====
_jobs: dict[str, dict[str, Any]] = {}

# 最大并发数上限
MAX_CONCURRENCY = 10


@dataclass
class SimpleRepo:
    """简化的仓库信息，兼容 TrendingRepo 和 Search API 结果。"""

    full_name: str
    description: str
    stars_today: int
    repo_url: str
    language: str = ""


class QuickGenRequest(BaseModel):
    """快速生成请求。"""

    language: str = Field(default="python", description="编程语言")
    max_results: int = Field(default=5, ge=1, le=1000, description="生成数量（1-1000）")
    concurrency: int = Field(default=5, ge=1, le=10, description="并发数（1-10，1为串行）")


class QuickArticle(BaseModel):
    """快速生成的文章。"""

    project_name: str
    project_url: str
    stars_today: int
    title: str
    body: str
    word_count: int
    model: str


class QuickGenStartResponse(BaseModel):
    """提交任务后的响应。"""

    job_id: str
    status: str = "pending"


class QuickGenStatusResponse(BaseModel):
    """轮询任务状态的响应。"""

    job_id: str
    status: str  # pending / running / completed / failed
    articles: list[QuickArticle] = []
    total: int = 0
    duration_sec: float = 0.0
    error: str = ""
    # 实时进度字段
    completed_count: int = 0
    total_count: int = 0
    current_projects: list[str] = []  # 正在处理的项目名


async def _discover_repos(language: str, max_results: int) -> list[SimpleRepo]:
    """发现 GitHub 项目。

    策略：
    - max_results <= 25: 使用 Trending（速度快，质量高）
    - max_results > 25: 使用 GitHub Search API 分页获取
    - 混合模式：先取 Trending，不够再从 Search API 补充
    """
    repos: list[SimpleRepo] = []
    seen: set[str] = set()

    # 1. 先从 Trending 获取（不需要 token）
    from services.discovery.trending_scraper import TrendingScraper

    scraper = TrendingScraper()
    try:
        # 获取多个时间范围的 trending
        for since in ("daily", "weekly"):
            if len(repos) >= max_results:
                break
            try:
                trending_repos = await scraper.fetch_trending(language=language, since=since)
                for r in trending_repos:
                    if r.full_name not in seen:
                        seen.add(r.full_name)
                        repos.append(SimpleRepo(
                            full_name=r.full_name,
                            description=r.description,
                            stars_today=r.stars_today,
                            repo_url=r.repo_url,
                            language=r.language,
                        ))
                        if len(repos) >= max_results:
                            break
            except Exception as e:
                logger.warning("trending_fetch_failed", since=since, error=str(e))
    finally:
        await scraper.close()

    logger.info("discover_trending", count=len(repos), needed=max_results)

    # 2. 如果不够，从 GitHub Search API 补充
    if len(repos) < max_results:
        remaining = max_results - len(repos)
        search_repos = await _search_repos_paginated(language, remaining, seen)
        repos.extend(search_repos)
        logger.info("discover_search_api", count=len(search_repos), total=len(repos))

    return repos[:max_results]


async def _search_repos_paginated(
    language: str, count: int, seen: set[str]
) -> list[SimpleRepo]:
    """通过 GitHub Search API 分页获取仓库。

    每页 100 个，最多 10 页 = 1000 个。
    未认证请求限流：10 次/分钟；认证后 5000 次/小时。
    """
    repos: list[SimpleRepo] = []
    settings = get_settings()
    gh_token = settings.github_token

    headers: dict[str, str] = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitCast/1.0",
    }
    if gh_token:
        headers["Authorization"] = f"token {gh_token}"

    # 构建搜索查询
    lang_filter = f"language:{language}" if language else "stars:>100"
    # 按星数排序，只取最近一年有更新的
    query = f"{lang_filter} stars:>50 pushed:>2025-01-01"

    per_page = min(100, count)
    pages_needed = (count + per_page - 1) // per_page
    pages_needed = min(pages_needed, 10)  # GitHub 限制最多 10 页

    async with httpx.AsyncClient(timeout=30) as client:
        for page in range(1, pages_needed + 1):
            if len(repos) >= count:
                break
            try:
                resp = await client.get(
                    "https://api.github.com/search/repositories",
                    headers=headers,
                    params={
                        "q": query,
                        "sort": "stars",
                        "order": "desc",
                        "per_page": per_page,
                        "page": page,
                    },
                )
                if resp.status_code == 403:
                    # 限流，等待后重试
                    logger.warning("github_rate_limited", page=page)
                    await asyncio.sleep(60)
                    continue
                if resp.status_code != 200:
                    logger.warning("search_api_error", status=resp.status_code, page=page)
                    break

                data = resp.json()
                items = data.get("items", [])
                if not items:
                    break

                for item in items:
                    full_name = item.get("full_name", "")
                    if not full_name or full_name in seen:
                        continue
                    seen.add(full_name)
                    repos.append(SimpleRepo(
                        full_name=full_name,
                        description=item.get("description", "") or "",
                        stars_today=item.get("stargazers_count", 0),
                        repo_url=item.get("html_url", f"https://github.com/{full_name}"),
                        language=item.get("language", "") or "",
                    ))
                    if len(repos) >= count:
                        break

                logger.info("search_api_page", page=page, got=len(items), total_repos=len(repos))

            except Exception as e:
                logger.warning("search_api_failed", page=page, error=str(e))
                break

    return repos


async def _fetch_readme(client: httpx.AsyncClient, full_name: str) -> str:
    """从 GitHub API 获取 README 内容，截取前 3000 字符作为上下文。"""
    try:
        resp = await client.get(
            f"https://api.github.com/repos/{full_name}/readme",
            headers={
                "Accept": "application/vnd.github.v3.raw",
                "User-Agent": "GitCast/1.0",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.text[:3000]
    except Exception:
        pass
    return ""


async def _run_generation(job_id: str, language: str, max_results: int, concurrency: int) -> None:
    """后台执行生成任务。"""
    start = time.perf_counter()
    settings = get_settings()
    job = _jobs[job_id]
    job["status"] = "running"

    try:
        # 1. 发现项目（Trending + Search API）
        job["current_projects"] = ["正在发现 GitHub 项目..."]
        repos = await _discover_repos(language, max_results)
        job["current_projects"] = []

        logger.info("quickgen_discover_done", job_id=job_id, count=len(repos))

        if not repos:
            job["status"] = "completed"
            job["articles"] = []
            job["total"] = 0
            job["duration_sec"] = 0.0
            return

        targets = repos[:max_results]
        job["total_count"] = len(targets)

        # 2. 生成文章
        api_key = settings.llm_api_key
        api_base = settings.llm_api_base
        model = settings.llm_model

        async def gen_one(repo: SimpleRepo) -> QuickArticle:
            # 获取 README 丰富上下文
            readme_content = ""
            try:
                async with httpx.AsyncClient(timeout=15) as gh_client:
                    readme_content = await _fetch_readme(gh_client, repo.full_name)
            except Exception:
                pass

            readme_section = ""
            if readme_content:
                readme_section = f"\n--- 项目 README（节选）---\n{readme_content}\n--- README 节选结束 ---\n"

            prompt = f"""请为以下 GitHub 开源项目写一篇详细、有深度的科普文章，面向对技术感兴趣但非专业开发者的读者。

项目: {repo.full_name}
描述: {repo.description or '暂无'}
今日新增星数: {repo.stars_today}
{readme_section}

写作要求：
1. 第一行是标题（不要加#号），标题要有吸引力，体现项目的核心价值
2. 正文 800-1200 字，分成以下几个部分（用空行分隔，不要加小标题前缀符号）：

   【开篇引子】用一个生活中的比喻或场景引入，让读者立刻明白这个项目解决什么问题
   【项目是什么】详细解释项目的核心功能和定位，不是简单复述描述，而是深入解读
   【技术原理】用通俗的比喻解释核心技术原理，让非技术人员也能理解它怎么工作的
   【核心功能】列举 2-3 个最有价值的功能，每个功能用 1-2 段详细说明
   【适合谁用】说明目标用户群体和具体使用场景
   【上手难度】评估学习成本，给出快速上手的建议
   【总结展望】这个项目为什么值得关注，未来可能的发展方向

3. 语言风格：像跟朋友聊天一样，生动有趣但信息密度高
4. 每个观点都要有具体例子或比喻支撑，不要空话
5. 适当使用类比、对比来帮助理解抽象概念
"""
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(
                        f"{api_base}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={
                            "model": model,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "你是资深科技博主和技术布道者，擅长用生动通俗的语言深入解读开源项目。你的文章信息密度高、有深度、能让读者真正学到知识。你善于用比喻和类比解释复杂技术，让非技术人员也能理解。每篇文章都要让读者觉得\u201c原来如此，我理解了\u201d。",
                                },
                                {"role": "user", "content": prompt},
                            ],
                            "max_tokens": 3000,
                            "temperature": 0.8,
                        },
                    )
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    lines = content.strip().split("\n")
                    title = lines[0].lstrip("#").strip()
                    body = "\n".join(lines[1:]).strip()

                    return QuickArticle(
                        project_name=repo.full_name,
                        project_url=repo.repo_url,
                        stars_today=repo.stars_today,
                        title=title,
                        body=body,
                        word_count=len(content),
                        model=model,
                    )
            except Exception as e:
                logger.error("quickgen_error", project=repo.full_name, error=str(e))
                return QuickArticle(
                    project_name=repo.full_name,
                    project_url=repo.repo_url,
                    stars_today=repo.stars_today,
                    title=f"生成失败: {repo.full_name}",
                    body=f"错误: {e}",
                    word_count=0,
                    model=model,
                )

        # 使用回调模式：每篇文章完成后立即写入 job，实现流式进度
        effective_concurrency = min(concurrency, MAX_CONCURRENCY)
        semaphore = asyncio.Semaphore(effective_concurrency)
        articles_lock = asyncio.Lock()

        async def gen_with_progress(repo: SimpleRepo, idx: int) -> QuickArticle:
            async with semaphore:
                # 记录正在处理的项目
                job["current_projects"].append(repo.full_name)
                try:
                    result = await gen_one(repo)
                finally:
                    # 完成后更新进度
                    async with articles_lock:
                        job["articles"].append(result.model_dump())
                        job["completed_count"] += 1
                        # 从当前处理列表中移除
                        if repo.full_name in job["current_projects"]:
                            job["current_projects"].remove(repo.full_name)
                    logger.info(
                        "quickgen_progress",
                        job_id=job_id,
                        completed=job["completed_count"],
                        total=job["total_count"],
                        project=repo.full_name,
                    )
                return result

        # 启动所有任务（通过信号量控制并发）
        tasks = [gen_with_progress(r, i) for i, r in enumerate(targets)]
        await asyncio.gather(*tasks)

        # 收集最终结果
        final_articles = job["articles"]

        duration = time.perf_counter() - start
        logger.info("quickgen_done", job_id=job_id, total=len(final_articles), duration=round(duration, 2))

        job["status"] = "completed"
        job["articles"] = final_articles
        job["total"] = len(final_articles)
        job["duration_sec"] = round(duration, 2)
        job["current_projects"] = []

    except Exception as e:
        logger.error("quickgen_failed", job_id=job_id, error=str(e))
        job["status"] = "failed"
        job["error"] = str(e)


@router.post("/run", response_model=QuickGenStartResponse)
async def quick_generate(request: QuickGenRequest) -> QuickGenStartResponse:
    """提交快速生成任务，立即返回 job_id。"""
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "status": "pending",
        "articles": [],
        "total": 0,
        "duration_sec": 0.0,
        "error": "",
        "completed_count": 0,
        "total_count": 0,
        "current_projects": [],
    }

    # 启动后台任务
    asyncio.create_task(
        _run_generation(job_id, request.language, request.max_results, request.concurrency)
    )

    logger.info(
        "quickgen_started",
        job_id=job_id,
        language=request.language,
        max=request.max_results,
        concurrency=request.concurrency,
    )
    return QuickGenStartResponse(job_id=job_id, status="pending")


@router.get("/status/{job_id}", response_model=QuickGenStatusResponse)
async def quickgen_status(job_id: str) -> QuickGenStatusResponse:
    """查询任务状态，支持实时进度和流式结果。"""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="任务不存在")

    job = _jobs[job_id]
    return QuickGenStatusResponse(
        job_id=job_id,
        status=job["status"],
        articles=job.get("articles", []),
        total=job.get("total", 0),
        duration_sec=job.get("duration_sec", 0.0),
        error=job.get("error", ""),
        completed_count=job.get("completed_count", 0),
        total_count=job.get("total_count", 0),
        current_projects=job.get("current_projects", []),
    )
