"""认证服务：注册、登录、Token 验证。

整合密码哈希、JWT 管理和用户/订阅模型。
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.subscription import PLAN_QUOTAS, Subscription, SubscriptionPlan
from models.user import User, UserRole
from services.auth.jwt_handler import JWTHandler, TokenPair
from services.auth.password import hash_password, verify_password
from shared.errors import AuthError
from shared.logging import get_logger

logger = get_logger(__name__)


class AuthService:
    """认证服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._jwt = JWTHandler()

    async def register(
        self,
        email: str,
        password: str,
        role: UserRole = UserRole.USER,
    ) -> tuple[User, TokenPair]:
        """注册新用户。

        Args:
            email: 邮箱
            password: 明文密码
            role: 用户角色

        Returns:
            (User, TokenPair)

        Raises:
            BusinessError: 邮箱已注册
        """
        # 检查邮箱是否已存在
        existing = await self._db.execute(
            select(User).where(User.email == email)
        )
        if existing.scalar_one_or_none():
            raise AuthError("该邮箱已注册", error_num=4)

        # 创建用户
        user = User(
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        self._db.add(user)
        await self._db.flush()

        # 创建免费订阅
        now = datetime.now(timezone.utc)
        subscription = Subscription(
            user_id=user.id,
            plan=SubscriptionPlan.FREE,
            api_quota_per_month=PLAN_QUOTAS[SubscriptionPlan.FREE],
            api_used_this_month=0,
            period_start=now,
            period_end=now + timedelta(days=30),
            is_active=True,
        )
        self._db.add(subscription)
        await self._db.commit()

        # 生成 token 对
        tokens = self._jwt.create_token_pair(str(user.id), user.role.value)

        logger.info("user_registered", user_id=str(user.id), email=email)
        return user, tokens

    async def login(self, email: str, password: str) -> tuple[User, TokenPair]:
        """用户登录。

        Args:
            email: 邮箱
            password: 明文密码

        Returns:
            (User, TokenPair)

        Raises:
            BusinessError: 邮箱或密码错误
        """
        result = await self._db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.password_hash):
            raise AuthError("邮箱或密码错误", error_num=5)

        if not user.is_active:
            raise AuthError("账户已被禁用", error_num=6)

        tokens = self._jwt.create_token_pair(str(user.id), user.role.value)
        logger.info("user_logged_in", user_id=str(user.id), email=email)
        return user, tokens

    async def get_user_by_id(self, user_id: str) -> User | None:
        """根据 ID 获取用户。"""
        result = await self._db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_by_api_key(self, api_key: str) -> User | None:
        """根据 API Key 获取用户（B端 API 认证）。"""
        result = await self._db.execute(
            select(User).where(User.api_key == api_key).where(User.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def refresh_token(self, refresh_token: str) -> TokenPair:
        """刷新 access token。"""
        return self._jwt.refresh_access_token(refresh_token)

    async def generate_api_key(self, user_id: str) -> str:
        """为用户生成 API Key。"""
        api_key = secrets.token_urlsafe(32)

        user = await self.get_user_by_id(user_id)
        if not user:
            raise AuthError("用户不存在", error_num=7)

        user.api_key = api_key
        await self._db.commit()

        logger.info("api_key_generated", user_id=user_id)
        return api_key

    def verify_access_token(self, token: str) -> dict[str, str]:
        """验证 access token，返回 payload。"""
        payload = self._jwt.verify_token(token, expected_type="access")
        return payload
