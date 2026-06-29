"""快速生成 API：不依赖数据库，异步发现项目+生成文章。

使用后台任务模式避免网关超时：
  POST /run  → 立即返回 job_id
  GET  /status/{job_id} → 轮询任务状态
"""

from __future__ import annotations

import asyncio
import time
import uuid
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


class QuickGenRequest(BaseModel):
    """快速生成请求。"""

    language: str = Field(default="python", description="编程语言")
    max_results: int = Field(default=3, ge=1, le=10, description="生成数量")


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


async def _run_generation(job_id: str, language: str, max_results: int) -> None:
    """后台执行生成任务。"""
    start = time.perf_counter()
    settings = get_settings()
    job = _jobs[job_id]
    job["status"] = "running"

    try:
        # 1. 发现热门项目
        from services.discovery.trending_scraper import TrendingScraper

        scraper = TrendingScraper()
        try:
            repos = await scraper.fetch_trending(language=language, since="daily")
            logger.info("quickgen_trending", job_id=job_id, count=len(repos))
        finally:
            await scraper.close()

        if not repos:
            job["status"] = "completed"
            job["articles"] = []
            job["total"] = 0
            job["duration_sec"] = 0.0
            return

        targets = repos[:max_results]

        # 2. 并发生成文章
        api_key = settings.llm_api_key
        api_base = settings.llm_api_base
        model = settings.llm_model

        async def fetch_readme(client: httpx.AsyncClient, full_name: str) -> str:
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
                    text = resp.text[:3000]
                    return text
            except Exception:
                pass
            return ""

        async def gen_one(repo: Any) -> QuickArticle:
            # 获取 README 丰富上下文
            readme_content = ""
            try:
                async with httpx.AsyncClient(timeout=15) as gh_client:
                    readme_content = await fetch_readme(gh_client, repo.full_name)
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

        # 并发执行（最多3个同时）
        semaphore = asyncio.Semaphore(3)

        async def gen_with_limit(repo: Any) -> QuickArticle:
            async with semaphore:
                return await gen_one(repo)

        articles = await asyncio.gather(*[gen_with_limit(r) for r in targets])

        duration = time.perf_counter() - start
        logger.info("quickgen_done", job_id=job_id, total=len(articles), duration=round(duration, 2))

        job["status"] = "completed"
        job["articles"] = [a.model_dump() for a in articles]
        job["total"] = len(articles)
        job["duration_sec"] = round(duration, 2)

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
    }

    # 启动后台任务
    asyncio.create_task(
        _run_generation(job_id, request.language, request.max_results)
    )

    logger.info("quickgen_started", job_id=job_id, language=request.language, max=request.max_results)
    return QuickGenStartResponse(job_id=job_id, status="pending")


@router.get("/status/{job_id}", response_model=QuickGenStatusResponse)
async def quickgen_status(job_id: str) -> QuickGenStatusResponse:
    """查询任务状态。"""
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
    )
