"""认证 API 端点：注册、登录、Token 刷新、个人信息。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db
from models.user import User, UserRole
from services.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    """注册请求。"""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.USER


class LoginRequest(BaseModel):
    """登录请求。"""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token 响应。"""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 1800


class UserResponse(BaseModel):
    """用户信息响应。"""

    id: str
    email: str
    role: str
    is_active: bool
    api_key: str | None = None


class RefreshRequest(BaseModel):
    """刷新 token 请求。"""

    refresh_token: str


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """注册新用户。"""
    auth_service = AuthService(db)
    _, tokens = await auth_service.register(
        email=request.email,
        password=request.password,
        role=request.role,
    )
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """用户登录。"""
    auth_service = AuthService(db)
    _, tokens = await auth_service.login(
        email=request.email,
        password=request.password,
    )
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """刷新 access token。"""
    auth_service = AuthService(db)
    tokens = await auth_service.refresh_token(request.refresh_token)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """获取当前用户信息。"""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        role=current_user.role.value,
        is_active=current_user.is_active,
        api_key=current_user.api_key,
    )


@router.post("/api-key", response_model=dict)
async def generate_api_key(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """生成 API Key（B端 API 调用用）。"""
    auth_service = AuthService(db)
    api_key = await auth_service.generate_api_key(str(current_user.id))
    return {"api_key": api_key}
