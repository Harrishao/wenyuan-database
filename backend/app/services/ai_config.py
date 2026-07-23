import base64
import hashlib
import json
import re
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.local_hashing_embedding import LocalHashingEmbedding
from app.adapters.openai_embedding import OpenAICompatibleEmbedding
from app.adapters.report_llm import LocalEvidenceDraftLlm, OpenAICompatibleLlm
from app.core.config import get_settings
from app.domain.models import EmbeddingPreset, LlmPreset, PromptPreset
from app.ports.llm import ChatMessage

settings = get_settings()
MACRO_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\}\}")


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.jwt_secret.get_secret_value().encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("密钥无法解密，请重新保存预设") from exc


async def get_active_llm_preset(session: AsyncSession) -> LlmPreset | None:
    return await session.scalar(select(LlmPreset).where(LlmPreset.is_active.is_(True)).limit(1))


async def get_active_prompt_preset(session: AsyncSession) -> PromptPreset | None:
    return await session.scalar(
        select(PromptPreset).where(PromptPreset.is_active.is_(True)).limit(1)
    )


async def get_active_embedding_preset(session: AsyncSession) -> EmbeddingPreset | None:
    return await session.scalar(
        select(EmbeddingPreset).where(EmbeddingPreset.is_active.is_(True)).limit(1)
    )


async def get_runtime_llm(
    session: AsyncSession,
) -> LocalEvidenceDraftLlm | OpenAICompatibleLlm:
    preset = await get_active_llm_preset(session)
    if preset is not None:
        key = decrypt_secret(preset.api_key_ciphertext)
        if key:
            return OpenAICompatibleLlm(
                preset.base_url,
                key,
                preset.model,
                float(preset.parameters.get("timeout_seconds", settings.llm_timeout_seconds)),
                {
                    key: value
                    for key, value in preset.parameters.items()
                    if key not in {"timeout_seconds", "max_retries"}
                },
                int(preset.parameters.get("max_retries", 2)),
            )
    if settings.llm_base_url and settings.llm_api_key and settings.llm_model:
        return OpenAICompatibleLlm(
            settings.llm_base_url,
            settings.llm_api_key.get_secret_value(),
            settings.llm_model,
            settings.llm_timeout_seconds,
        )
    return LocalEvidenceDraftLlm()


async def get_runtime_embedding(
    session: AsyncSession,
) -> LocalHashingEmbedding | OpenAICompatibleEmbedding:
    preset = await get_active_embedding_preset(session)
    if preset is None or preset.provider == "local_hashing":
        return LocalHashingEmbedding(preset.dimensions if preset else settings.embedding_dimensions)
    key = decrypt_secret(preset.api_key_ciphertext)
    if not preset.base_url or not key:
        raise ValueError("第三方向量预设缺少 Base URL 或 API Key")
    return OpenAICompatibleEmbedding(
        base_url=preset.base_url,
        api_key=key,
        model=preset.model,
        dimensions=preset.dimensions,
        parameters={
            key: value for key, value in preset.parameters.items() if key != "timeout_seconds"
        },
        timeout_seconds=float(preset.parameters.get("timeout_seconds", 120)),
    )


def _resolve_macro(path: str, variables: dict[str, Any]) -> str:
    current: Any = variables
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return ""
        current = current[part]
    if isinstance(current, (dict, list)):
        return json.dumps(current, ensure_ascii=False)
    return "" if current is None else str(current)


def render_macro_text(template: str, variables: dict[str, Any]) -> str:
    return MACRO_PATTERN.sub(lambda match: _resolve_macro(match.group(1), variables), template)


def render_prompt_messages(
    preset: PromptPreset | None,
    variables: dict[str, Any],
    fallback: list[ChatMessage],
) -> list[ChatMessage]:
    if preset is None:
        return fallback
    messages = sorted(
        (item for item in preset.messages if item.get("enabled", True)),
        key=lambda item: int(item.get("position", 0)),
    )
    rendered = [
        ChatMessage(
            role=item["role"],
            content=render_macro_text(str(item.get("content", "")), variables),
        )
        for item in messages
        if item.get("role") in {"system", "user", "assistant"}
    ]
    return rendered or fallback


async def activate_embedding_preset(session: AsyncSession, preset_id: UUID) -> None:
    presets = list(await session.scalars(select(EmbeddingPreset)))
    for item in presets:
        item.is_active = item.id == preset_id


async def activate_prompt_preset(session: AsyncSession, preset_id: UUID) -> None:
    presets = list(await session.scalars(select(PromptPreset)))
    for item in presets:
        item.is_active = item.id == preset_id
