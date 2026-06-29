"""密码哈希工具，基于 passlib + bcrypt。

遵循安全规范：不存储明文密码，使用 bcrypt 哈希。
bcrypt 限制：密码最长 72 字节，超出部分截断。
"""

from __future__ import annotations

from passlib.context import CryptContext

# bcrypt 哈希上下文
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt 限制密码最大 72 字节
_MAX_PASSWORD_BYTES = 72


def _truncate_password(password: str) -> str:
    """截断密码到 bcrypt 允许的最大长度（72 字节）。"""
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        encoded = encoded[:_MAX_PASSWORD_BYTES]
    return encoded.decode("utf-8", errors="ignore")


def hash_password(password: str) -> str:
    """对密码进行 bcrypt 哈希。

    Args:
        password: 明文密码

    Returns:
        bcrypt 哈希字符串
    """
    safe_password = _truncate_password(password)
    hashed: str = _pwd_context.hash(safe_password)
    return hashed


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码是否匹配。

    Args:
        plain_password: 明文密码
        hashed_password: 哈希后的密码

    Returns:
        是否匹配
    """
    safe_password = _truncate_password(plain_password)
    result: bool = _pwd_context.verify(safe_password, hashed_password)
    return result
