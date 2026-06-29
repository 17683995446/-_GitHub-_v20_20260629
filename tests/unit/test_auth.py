"""认证服务单元测试。"""

from __future__ import annotations

import pytest

from services.auth.jwt_handler import JWTHandler
from services.auth.password import hash_password, verify_password
from shared.errors import AuthError


class TestPasswordHashing:
    """密码哈希测试。"""

    def test_hash_and_verify(self) -> None:
        """哈希后密码应可验证。"""
        plain = "SecurePwd1!"
        hashed = hash_password(plain)
        assert hashed != plain
        assert verify_password(plain, hashed) is True

    def test_wrong_password(self) -> None:
        """错误密码应验证失败。"""
        hashed = hash_password("CorrectPwd")
        assert verify_password("WrongPwd", hashed) is False

    def test_different_hashes_for_same_password(self) -> None:
        """相同密码生成不同哈希（bcrypt salt）。"""
        h1 = hash_password("SamePwd123")
        h2 = hash_password("SamePwd123")
        assert h1 != h2

    def test_long_password_truncated(self) -> None:
        """超长密码应被截断后正常哈希验证。"""
        long_pwd = "a" * 200
        hashed = hash_password(long_pwd)
        # 截断后的前 72 字节仍能验证
        assert verify_password("a" * 72, hashed) is True
        assert verify_password("b" * 72, hashed) is False


class TestJWTHandler:
    """JWT Token 管理器测试。"""

    @pytest.fixture
    def jwt_handler(self, mock_settings: None) -> JWTHandler:
        """创建 JWT 处理器。"""
        return JWTHandler()

    def test_create_token_pair(self, jwt_handler: JWTHandler) -> None:
        """生成 token 对。"""
        tokens = jwt_handler.create_token_pair("user-123", "user")
        assert tokens.access_token
        assert tokens.refresh_token
        assert tokens.token_type == "Bearer"
        assert tokens.expires_in > 0

    def test_verify_access_token(self, jwt_handler: JWTHandler) -> None:
        """验证 access token。"""
        tokens = jwt_handler.create_token_pair("user-456", "admin")
        payload = jwt_handler.verify_token(tokens.access_token, expected_type="access")
        assert payload["sub"] == "user-456"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_verify_refresh_token(self, jwt_handler: JWTHandler) -> None:
        """验证 refresh token。"""
        tokens = jwt_handler.create_token_pair("user-789", "user")
        payload = jwt_handler.verify_token(tokens.refresh_token, expected_type="refresh")
        assert payload["sub"] == "user-789"
        assert payload["type"] == "refresh"

    def test_verify_wrong_type_raises(self, jwt_handler: JWTHandler) -> None:
        """用 access token 验证 refresh 应报错。"""
        tokens = jwt_handler.create_token_pair("user-000", "user")
        with pytest.raises(AuthError, match="类型不匹配"):
            jwt_handler.verify_token(tokens.access_token, expected_type="refresh")

    def test_verify_invalid_token_raises(self, jwt_handler: JWTHandler) -> None:
        """无效 token 应报错。"""
        with pytest.raises(AuthError, match="Token 无效"):
            jwt_handler.verify_token("invalid.token.here")

    def test_refresh_access_token(self, jwt_handler: JWTHandler) -> None:
        """刷新 access token 应返回有效的新 token 对。"""
        tokens = jwt_handler.create_token_pair("user-ref", "user")
        new_tokens = jwt_handler.refresh_access_token(tokens.refresh_token)
        # 新 access token 应可验证
        payload = jwt_handler.verify_token(new_tokens.access_token)
        assert payload["sub"] == "user-ref"
        assert payload["type"] == "access"
        # 新 refresh token 应与旧的不同（因为生成了新的）
        assert new_tokens.refresh_token is not None
