from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Cookie, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    token_digest,
    verify_password,
)
from app.domain.enums import UserStatus
from app.domain.models import RefreshToken, User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse

router = APIRouter()
settings = get_settings()
REFRESH_COOKIE = "wenyuan_refresh"


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path=f"{settings.api_prefix}/auth",
    )


def auth_response(user: User, access_token: str) -> AuthResponse:
    return AuthResponse(
        access_token=access_token,
        expires_in=settings.access_token_minutes * 60,
        user=UserResponse.model_validate(user),
    )


async def issue_tokens(session: SessionDep, response: Response, user: User) -> AuthResponse:
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_digest(refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        )
    )
    await session.commit()
    set_refresh_cookie(response, refresh_token)
    return auth_response(user, access_token)


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    payload: RegisterRequest, session: SessionDep, response: Response
) -> AuthResponse:
    user = User(
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError("AUTH_EMAIL_EXISTS", "该邮箱已注册", status_code=409) from exc
    return await issue_tokens(session, response, user)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, session: SessionDep, response: Response) -> AuthResponse:
    user = await session.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppError("AUTH_CREDENTIALS_INVALID", "邮箱或密码错误", status_code=401)
    if user.status != UserStatus.ACTIVE:
        raise AppError("AUTH_USER_DISABLED", "账号已被禁用", status_code=403)
    return await issue_tokens(session, response, user)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    response: Response,
    session: SessionDep,
    wenyuan_refresh: str | None = Cookie(default=None),
) -> AuthResponse:
    if not wenyuan_refresh:
        raise AppError("AUTH_REFRESH_REQUIRED", "刷新凭证缺失", status_code=401)
    payload = decode_token(wenyuan_refresh, "refresh")
    stored = await session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_digest(wenyuan_refresh),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(UTC),
        )
    )
    if stored is None:
        raise AppError("AUTH_REFRESH_INVALID", "刷新凭证已失效", status_code=401)
    user = await session.get(User, UUID(payload["sub"]))
    if user is None or user.status != UserStatus.ACTIVE:
        raise AppError("AUTH_USER_DISABLED", "账号不可用", status_code=403)
    stored.revoked_at = datetime.now(UTC)
    return await issue_tokens(session, response, user)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    session: SessionDep,
    wenyuan_refresh: str | None = Cookie(default=None),
) -> None:
    if wenyuan_refresh:
        stored = await session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_digest(wenyuan_refresh),
                RefreshToken.revoked_at.is_(None),
            )
        )
        if stored:
            stored.revoked_at = datetime.now(UTC)
            await session.commit()
    response.delete_cookie(REFRESH_COOKIE, path=f"{settings.api_prefix}/auth")


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
