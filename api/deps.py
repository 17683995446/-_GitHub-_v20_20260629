"""FastAPI 依赖注入。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User, UserRole
from services.auth.service import AuthService
from shared.database import get_session_maker
from shared.errors import AuthError


async def get_db() -> AsyncIterator[AsyncSession]:
    """获取数据库会话依赖。

    与 shared.database.get_db 功能相同，但作为 API 层入口点，
    方便后续扩展（如注入 tenant_id 等）。
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 Authorization header 提取并验证当前用户。

    支持两种认证方式：
    1. Bearer JWT token（C端用户）
    2. X-API-Key header（B端 API 用户，通过 get_user_by_api_key）

    Raises:
        BusinessError: 未提供认证信息或认证失败
    """
    if not authorization:
        raise AuthError("未提供认证信息", error_num=8)

    # 去掉 "Bearer " 前缀
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError("认证格式错误，应为 Bearer <token>", error_num=9)

    token = parts[1]
    auth_service = AuthService(db)

    try:
        payload = auth_service.verify_access_token(token)
    except AuthError:
        # 尝试作为 API Key 验证
        user = await auth_service.get_user_by_api_key(token)
        if user is None:
            raise
        return user
    else:
        user_id = payload["sub"]
        user = await auth_service.get_user_by_id(user_id)
        if user is None:
            raise AuthError("用户不存在", error_num=7)
        if not user.is_active:
            raise AuthError("账户已被禁用", error_num=6)
        return user


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """要求当前用户是管理员。"""
    if current_user.role != UserRole.ADMIN:
        raise AuthError("需要管理员权限", error_num=10)
    return current_user
