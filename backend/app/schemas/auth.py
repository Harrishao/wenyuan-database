from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.enums import UserRole, UserStatus


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    display_name: str
    avatar_url: str | None
    bio: str | None
    email_verified: bool
    role: UserRole
    status: UserStatus
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class EmailCodeRequest(BaseModel):
    email: EmailStr
    purpose: Literal["verify_email", "reset_password"]


class EmailCodeConfirm(BaseModel):
    email: EmailStr
    purpose: Literal["verify_email", "reset_password"]
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str | None = Field(default=None, min_length=8, max_length=128)
