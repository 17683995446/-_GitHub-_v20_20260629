"""健康检查端点。"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """健康检查。"""
    return {"status": "ok", "service": "gitcast"}


@router.get("/health/ready")
async def readiness_check() -> dict[str, str]:
    """就绪检查（含数据库连接验证）。"""
    from shared.database import get_engine

    engine = get_engine()
    return {
        "status": "ready",
        "database": "configured" if engine else "not_configured",
    }
