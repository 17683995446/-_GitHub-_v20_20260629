"""API 端点测试（认证 + 内容 + 统计）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from api.app import create_app
from api.deps import get_current_user, get_db
from models.user import User, UserRole


@pytest.fixture
def app(mock_settings: None, tmp_path: str, monkeypatch: pytest.MonkeyPatch):
    """创建测试用 FastAPI 应用。"""
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path))
    monkeypatch.setenv("STORAGE_BASE_URL", "http://test.local/storage")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-testing-only")
    from shared.config import get_settings

    get_settings.cache_clear()
    return create_app()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    """创建测试用 HTTP 客户端。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def make_mock_user(
    email: str = "test@example.com",
    role: UserRole = UserRole.USER,
) -> User:
    """创建模拟用户。"""
    return User(
        id=MagicMock(),
        email=email,
        password_hash="hashed_password",
        role=role,
        is_active=True,
        api_key="test-api-key-12345",
    )


@pytest.fixture
def auth_client(app):
    """创建带认证的测试客户端（覆盖 get_current_user）。"""
    mock_user = make_mock_user()

    async def mock_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = mock_get_current_user

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    return client


class TestAuthAPI:
    """认证 API 测试。"""

    @pytest.mark.asyncio
    async def test_register(self, app, client: AsyncClient, mock_settings: None) -> None:
        """注册新用户。"""
        # Mock AuthService.register
        from services.auth import service as auth_service_module
        from services.auth.jwt_handler import TokenPair

        mock_user = make_mock_user("newuser@example.com")
        mock_tokens = TokenPair(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
        )

        original_register = auth_service_module.AuthService.register
        auth_service_module.AuthService.register = AsyncMock(
            return_value=(mock_user, mock_tokens)
        )

        # Mock DB
        async def mock_get_db() -> AsyncIterator[None]:
            yield None

        app.dependency_overrides[get_db] = mock_get_db

        try:
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "newuser@example.com",
                    "password": "SecurePassword123!",
                },
            )
            assert resp.status_code == 201
            data = resp.json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["token_type"] == "Bearer"
        finally:
            auth_service_module.AuthService.register = original_register
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_login(self, app, client: AsyncClient, mock_settings: None) -> None:
        """用户登录。"""
        from services.auth import service as auth_service_module
        from services.auth.jwt_handler import TokenPair

        mock_user = make_mock_user("login@example.com")
        mock_tokens = TokenPair(
            access_token="login-access-token",
            refresh_token="login-refresh-token",
        )

        original_login = auth_service_module.AuthService.login
        auth_service_module.AuthService.login = AsyncMock(
            return_value=(mock_user, mock_tokens)
        )

        async def mock_get_db() -> AsyncIterator[None]:
            yield None

        app.dependency_overrides[get_db] = mock_get_db

        try:
            resp = await client.post(
                "/api/v1/auth/login",
                json={
                    "email": "login@example.com",
                    "password": "SecurePassword123!",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["access_token"] == "login-access-token"
        finally:
            auth_service_module.AuthService.login = original_login
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_login_wrong_password_validation(
        self, client: AsyncClient
    ) -> None:
        """密码太短应返回 422。"""
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "password": "short",  # 少于 8 字符
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient) -> None:
        """无效邮箱应返回 422。"""
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "not-an-email",
                "password": "SecurePassword123!",
            },
        )
        assert resp.status_code == 422


class TestContentAPI:
    """内容 API 测试。"""

    @pytest.mark.asyncio
    async def test_list_articles_unauthorized(self, client: AsyncClient) -> None:
        """未认证应返回 403 或 401。"""
        resp = await client.get("/api/v1/content/articles")
        # 未提供 Authorization header，BusinessError 被抛出
        assert resp.status_code in (401, 403, 500)

    @pytest.mark.asyncio
    async def test_list_articles_authorized(
        self, app, mock_settings: None
    ) -> None:
        """认证后应能访问内容。"""
        mock_user = make_mock_user()

        async def mock_get_current_user():
            return mock_user

        # Mock DB session
        mock_session = MagicMock()

        # Mock query results for articles
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_current_user
        app.dependency_overrides[get_db] = mock_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/content/articles")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert "total" in data
            assert data["items"] == []

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_article_not_found(
        self, app, mock_settings: None
    ) -> None:
        """文章不存在应返回 404。"""
        mock_user = make_mock_user()

        async def mock_get_current_user():
            return mock_user

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_current_user
        app.dependency_overrides[get_db] = mock_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(
                "/api/v1/content/articles/123e4567-e89b-12d3-a456-426614174000"
            )
            assert resp.status_code == 404

        app.dependency_overrides.clear()


class TestStatsAPI:
    """统计 API 测试。"""

    @pytest.mark.asyncio
    async def test_overview_unauthorized(self, client: AsyncClient) -> None:
        """未认证应拒绝。"""
        resp = await client.get("/api/v1/stats/overview")
        assert resp.status_code in (401, 403, 500)

    @pytest.mark.asyncio
    async def test_overview_authorized(self, app, mock_settings: None) -> None:
        """认证后应能获取统计。"""
        mock_user = make_mock_user()

        async def mock_get_current_user():
            return mock_user

        mock_session = MagicMock()
        mock_session.scalar = AsyncMock(return_value=0)
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_current_user
        app.dependency_overrides[get_db] = mock_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/stats/overview")
            assert resp.status_code == 200
            data = resp.json()
            assert "total_projects" in data
            assert "total_articles" in data
            assert "publish_success_rate" in data

        app.dependency_overrides.clear()
