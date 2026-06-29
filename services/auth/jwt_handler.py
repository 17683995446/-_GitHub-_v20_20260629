"""JWT Token 管理器。

使用 PyJWT 生成和验证 access/refresh token。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from shared.config import get_settings
from shared.errors import AuthError
from shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TokenPair:
    """Token 对：access + refresh。"""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 1800  # 30 分钟


class JWTHandler:
    """JWT Token 管理器。

    - access_token：短期（30 分钟），用于 API 认证
    - refresh_token：长期（7 天），用于刷新 access_token
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    def create_token_pair(self, user_id: str, role: str) -> TokenPair:
        """生成 access + refresh token 对。"""
        now = datetime.now(timezone.utc)

        access_expire = now + timedelta(
            minutes=self._settings.jwt_access_token_expire_minutes
        )
        refresh_expire = now + timedelta(
            days=self._settings.jwt_refresh_token_expire_days
        )

        access_payload = {
            "sub": user_id,
            "role": role,
            "type": "access",
            "exp": access_expire,
            "iat": now,
        }
        refresh_payload = {
            "sub": user_id,
            "role": role,
            "type": "refresh",
            "exp": refresh_expire,
            "iat": now,
        }

        secret = self._settings.secret_key or "dev-secret-key-change-in-production"
        algorithm = self._settings.jwt_algorithm

        access_token = jwt.encode(access_payload, secret, algorithm=algorithm)
        refresh_token = jwt.encode(refresh_payload, secret, algorithm=algorithm)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self._settings.jwt_access_token_expire_minutes * 60,
        )

    def verify_token(self, token: str, expected_type: str = "access") -> dict[str, Any]:
        """验证并解码 JWT token。

        Args:
            token: JWT token 字符串
            expected_type: 期望的 token 类型（access / refresh）

        Returns:
            解码后的 payload

        Raises:
            BusinessError: token 无效或过期
        """
        secret = self._settings.secret_key or "dev-secret-key-change-in-production"
        algorithm = self._settings.jwt_algorithm

        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                secret,
                algorithms=[algorithm],
            )
        except jwt.ExpiredSignatureError as e:
            raise AuthError("Token 已过期", error_num=1) from e
        except jwt.InvalidTokenError as e:
            raise AuthError(f"Token 无效: {e}", error_num=2) from e

        if payload.get("type") != expected_type:
            raise AuthError(
                f"Token 类型不匹配，期望 {expected_type}",
                error_num=3,
            )

        return payload

    def refresh_access_token(self, refresh_token: str) -> TokenPair:
        """使用 refresh_token 刷新 access_token。"""
        payload = self.verify_token(refresh_token, expected_type="refresh")
        user_id = payload["sub"]
        role = payload["role"]
        return self.create_token_pair(user_id, role)
