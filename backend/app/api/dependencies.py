from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import decode_token
from app.db.session import get_session
from app.domain.enums import UserRole, UserStatus
from app.domain.models import User

bearer_scheme = HTTPBearer(auto_error=False)
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise AppError("AUTH_REQUIRED", "请先登录", status_code=401)
    payload = decode_token(credentials.credentials, "access")
    try:
        user_id = UUID(payload["sub"])
    except (ValueError, TypeError) as exc:
        raise AppError("AUTH_TOKEN_INVALID", "登录凭证无效", status_code=401) from exc
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("AUTH_USER_NOT_FOUND", "用户不存在", status_code=401)
    if user.status != UserStatus.ACTIVE:
        raise AppError("AUTH_USER_DISABLED", "账号已被禁用", status_code=403)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_admin_user(current_user: CurrentUser) -> User:
    if current_user.role != UserRole.ADMIN:
        raise AppError("ADMIN_REQUIRED", "需要管理员权限", status_code=403)
    return current_user


AdminUser = Annotated[User, Depends(get_admin_user)]
