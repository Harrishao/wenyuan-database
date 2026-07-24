from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.domain.enums import UserRole
from app.domain.models import (
    ChatConversation,
    ChatRecord,
    CreditLedger,
    Document,
    LlmPreset,
    Report,
    ReportVersion,
    User,
)
from app.ports.llm import LlmUsage


def month_start() -> datetime:
    timezone = ZoneInfo("Asia/Shanghai")
    now = datetime.now(timezone)
    return datetime(now.year, now.month, 1, tzinfo=timezone).astimezone(UTC)


async def credit_balance(session: AsyncSession, user: User) -> Decimal | None:
    if user.role == UserRole.ADMIN or user.monthly_credits is None:
        return None
    delta = await session.scalar(
        select(func.coalesce(func.sum(CreditLedger.amount), 0)).where(
            CreditLedger.user_id == user.id,
            CreditLedger.created_at >= month_start(),
        )
    )
    return Decimal(user.monthly_credits) + Decimal(delta or 0)


async def ensure_credits(session: AsyncSession, user: User) -> None:
    balance = await credit_balance(session, user)
    if balance is not None and balance <= 0:
        raise AppError("CREDITS_EXHAUSTED", "本期 Credits 已用完", status_code=402)


async def record_llm_usage(
    session: AsyncSession,
    user_id: UUID,
    usage: LlmUsage,
    model: str,
    operation: str,
) -> Decimal:
    preset = await session.scalar(select(LlmPreset).where(LlmPreset.is_active.is_(True)).limit(1))
    if preset is None or usage.total_tokens == 0:
        return Decimal("0")
    if preset.usage_mode == "auto":
        preset.usage_mode = "estimated" if usage.estimated else "reported"
    cost = (
        Decimal(usage.input_tokens) * Decimal(preset.input_credits_per_million_tokens)
        + Decimal(usage.output_tokens) * Decimal(preset.output_credits_per_million_tokens)
    ) / Decimal(1_000_000)
    session.add(
        CreditLedger(
            user_id=user_id,
            kind="usage",
            amount=-cost,
            operation=operation,
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            estimated=usage.estimated,
            details={"llm_preset_id": str(preset.id)},
        )
    )
    return cost


async def storage_used_bytes(session: AsyncSession, user_id: UUID) -> int:
    documents = await session.scalar(
        select(func.coalesce(func.sum(Document.file_size), 0)).where(
            Document.uploaded_by == user_id
        )
    )
    reports = await session.scalar(
        select(func.coalesce(func.sum(func.octet_length(ReportVersion.content_markdown)), 0))
        .join(Report, Report.id == ReportVersion.report_id)
        .where(Report.owner_id == user_id)
    )
    chats = await session.scalar(
        select(func.coalesce(func.sum(func.octet_length(ChatRecord.content)), 0))
        .join(
            ChatConversation,
            ChatConversation.id == ChatRecord.conversation_id,
        )
        .where(ChatConversation.owner_id == user_id)
    )
    return int(documents or 0) + int(reports or 0) + int(chats or 0)


async def ensure_storage(session: AsyncSession, user: User, additional_bytes: int = 0) -> int:
    used = await storage_used_bytes(session, user.id)
    if (
        user.role != UserRole.ADMIN
        and user.storage_quota_bytes is not None
        and used + max(0, additional_bytes) > user.storage_quota_bytes
    ):
        raise AppError("STORAGE_QUOTA_EXCEEDED", "硬盘配额不足", status_code=413)
    return used
