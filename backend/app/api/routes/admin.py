import csv
from datetime import UTC, datetime
from io import StringIO
from uuid import UUID

import httpx
import psutil
from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import AdminUser, SessionDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import recent_logs
from app.domain.enums import ProcessingStatus, TemplateStatus
from app.domain.models import (
    AuditLog,
    BackgroundJob,
    Document,
    EmbeddingPreset,
    LlmPreset,
    PromptPreset,
    RefreshToken,
    Report,
    ReportTemplate,
    SensitiveTerm,
    TemplateSection,
    TemplateVersion,
    User,
)
from app.schemas.admin import (
    ActivatePresetRequest,
    AdminTemplateVersionCreate,
    AdminUserResponse,
    AdminUserUpdate,
    ApplicationLogResponse,
    AuditLogResponse,
    EmbeddingPresetInput,
    EmbeddingPresetResponse,
    LlmPresetInput,
    LlmPresetResponse,
    ModelListResponse,
    PromptPresetInput,
    PromptPresetResponse,
    RuntimeConfigResponse,
    SensitiveGroupInput,
    SensitiveGroupResponse,
    SensitiveTermImport,
    SensitiveTermInput,
    SensitiveTermResponse,
    ServerStatusResponse,
)
from app.services.ai_config import (
    activate_embedding_preset,
    activate_prompt_preset,
    decrypt_secret,
    encrypt_secret,
    get_active_embedding_preset,
    get_active_llm_preset,
    get_active_prompt_preset,
)
from app.services.document_processing import process_document

router = APIRouter()
settings = get_settings()
process = psutil.Process()


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def add_audit(
    session: SessionDep,
    admin: User,
    request: Request,
    action: str,
    target_type: str,
    target_id: UUID | str | None,
    details: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_user_id=admin.id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            result="succeeded",
            details=details or {},
            ip_address=client_ip(request),
        )
    )


def prompt_response(item: PromptPreset) -> PromptPresetResponse:
    return PromptPresetResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        messages=item.messages,
        version=item.version,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def llm_response(item: LlmPreset) -> LlmPresetResponse:
    return LlmPresetResponse(
        id=item.id,
        name=item.name,
        base_url=item.base_url,
        model=item.model,
        parameters=item.parameters,
        has_api_key=bool(item.api_key_ciphertext),
        version=item.version,
        is_active=item.is_active,
        bound_prompt_preset_id=item.bound_prompt_preset_id,
        bound_embedding_preset_id=item.bound_embedding_preset_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def embedding_response(item: EmbeddingPreset) -> EmbeddingPresetResponse:
    return EmbeddingPresetResponse(
        id=item.id,
        name=item.name,
        provider=item.provider,
        base_url=item.base_url,
        model=item.model,
        dimensions=item.dimensions,
        parameters=item.parameters,
        has_api_key=bool(item.api_key_ciphertext),
        version=item.version,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(session: SessionDep, admin: AdminUser) -> list[AdminUserResponse]:
    del admin
    rows = (
        await session.execute(
            select(
                User,
                func.count(func.distinct(Document.id)),
                func.count(func.distinct(Report.id)),
            )
            .outerjoin(Document, Document.uploaded_by == User.id)
            .outerjoin(Report, Report.owner_id == User.id)
            .group_by(User.id)
            .order_by(User.created_at.desc())
        )
    ).all()
    return [
        AdminUserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            status=user.status,
            document_count=document_count,
            report_count=report_count,
            created_at=user.created_at,
        )
        for user, document_count, report_count in rows
    ]


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: UUID,
    payload: AdminUserUpdate,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> AdminUserResponse:
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("ADMIN_USER_NOT_FOUND", "用户不存在", status_code=404)
    if user.id == admin.id and payload.status.value == "disabled":
        raise AppError("ADMIN_SELF_DISABLE", "不能禁用当前管理员", status_code=409)
    user.status = payload.status
    if payload.status.value == "disabled":
        await session.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
    add_audit(session, admin, request, "user.status.update", "user", user.id, payload.model_dump())
    await session.commit()
    document_count = await session.scalar(
        select(func.count(Document.id)).where(Document.uploaded_by == user.id)
    )
    report_count = await session.scalar(
        select(func.count(Report.id)).where(Report.owner_id == user.id)
    )
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
        document_count=document_count or 0,
        report_count=report_count or 0,
        created_at=user.created_at,
    )


@router.get("/llm-presets", response_model=list[LlmPresetResponse])
async def list_llm_presets(session: SessionDep, admin: AdminUser) -> list[LlmPresetResponse]:
    del admin
    return [
        llm_response(item)
        for item in await session.scalars(select(LlmPreset).order_by(LlmPreset.name))
    ]


@router.post("/llm-presets", response_model=LlmPresetResponse, status_code=201)
async def create_llm_preset(
    payload: LlmPresetInput,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> LlmPresetResponse:
    item = LlmPreset(
        name=payload.name.strip(),
        base_url=payload.base_url.strip().rstrip("/"),
        api_key_ciphertext=encrypt_secret(payload.api_key),
        model=payload.model.strip(),
        parameters=payload.parameters,
        bound_prompt_preset_id=payload.bound_prompt_preset_id,
        bound_embedding_preset_id=payload.bound_embedding_preset_id,
        created_by=admin.id,
    )
    session.add(item)
    try:
        await session.flush()
        add_audit(session, admin, request, "llm_preset.create", "llm_preset", item.id)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError("PRESET_NAME_EXISTS", "预设名称已存在", status_code=409) from exc
    await session.refresh(item)
    return llm_response(item)


@router.put("/llm-presets/{preset_id}", response_model=LlmPresetResponse)
async def update_llm_preset(
    preset_id: UUID,
    payload: LlmPresetInput,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> LlmPresetResponse:
    item = await session.get(LlmPreset, preset_id)
    if item is None:
        raise AppError("LLM_PRESET_NOT_FOUND", "LLM 预设不存在", status_code=404)
    item.name = payload.name.strip()
    item.base_url = payload.base_url.strip().rstrip("/")
    item.model = payload.model.strip()
    item.parameters = payload.parameters
    item.bound_prompt_preset_id = payload.bound_prompt_preset_id
    item.bound_embedding_preset_id = payload.bound_embedding_preset_id
    item.version += 1
    if payload.api_key:
        item.api_key_ciphertext = encrypt_secret(payload.api_key)
    add_audit(session, admin, request, "llm_preset.update", "llm_preset", item.id)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError("PRESET_NAME_EXISTS", "预设名称已存在", status_code=409) from exc
    await session.refresh(item)
    return llm_response(item)


@router.delete("/llm-presets/{preset_id}", status_code=204)
async def delete_llm_preset(
    preset_id: UUID,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> None:
    item = await session.get(LlmPreset, preset_id)
    if item is None:
        raise AppError("LLM_PRESET_NOT_FOUND", "LLM 预设不存在", status_code=404)
    if item.is_active:
        raise AppError("PRESET_IS_ACTIVE", "请先切换到其他 LLM 预设", status_code=409)
    add_audit(session, admin, request, "llm_preset.delete", "llm_preset", item.id)
    await session.delete(item)
    await session.commit()


@router.post("/llm-presets/{preset_id}/activate", response_model=RuntimeConfigResponse)
async def activate_llm(
    preset_id: UUID,
    payload: ActivatePresetRequest,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> RuntimeConfigResponse:
    item = await session.get(LlmPreset, preset_id)
    if item is None:
        raise AppError("LLM_PRESET_NOT_FOUND", "LLM 预设不存在", status_code=404)
    await session.execute(update(LlmPreset).values(is_active=False))
    item.is_active = True
    if payload.sync_bindings and item.bound_prompt_preset_id:
        await activate_prompt_preset(session, item.bound_prompt_preset_id)
    if payload.sync_bindings and item.bound_embedding_preset_id:
        await activate_embedding_preset(session, item.bound_embedding_preset_id)
    add_audit(
        session,
        admin,
        request,
        "llm_preset.activate",
        "llm_preset",
        item.id,
        {"sync_bindings": payload.sync_bindings},
    )
    await session.commit()
    prompt = await get_active_prompt_preset(session)
    embedding = await get_active_embedding_preset(session)
    return RuntimeConfigResponse(
        llm_preset_id=item.id,
        prompt_preset_id=prompt.id if prompt else None,
        embedding_preset_id=embedding.id if embedding else None,
        source="database",
    )


@router.get("/llm-presets/{preset_id}/models", response_model=ModelListResponse)
async def fetch_llm_models(
    preset_id: UUID, session: SessionDep, admin: AdminUser
) -> ModelListResponse:
    del admin
    item = await session.get(LlmPreset, preset_id)
    if item is None:
        raise AppError("LLM_PRESET_NOT_FOUND", "LLM 预设不存在", status_code=404)
    key = decrypt_secret(item.api_key_ciphertext)
    if not key:
        raise AppError("LLM_PRESET_KEY_MISSING", "该预设没有 API Key", status_code=409)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{item.base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {key}"},
        )
    if not response.is_success:
        raise AppError("LLM_MODEL_FETCH_FAILED", "模型列表拉取失败", status_code=502)
    models = sorted(str(row["id"]) for row in response.json().get("data", []) if row.get("id"))
    return ModelListResponse(models=models)


@router.get("/prompt-presets", response_model=list[PromptPresetResponse])
async def list_prompt_presets(session: SessionDep, admin: AdminUser) -> list[PromptPresetResponse]:
    del admin
    return [
        prompt_response(item)
        for item in await session.scalars(select(PromptPreset).order_by(PromptPreset.name))
    ]


@router.post("/prompt-presets", response_model=PromptPresetResponse, status_code=201)
async def create_prompt_preset(
    payload: PromptPresetInput,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> PromptPresetResponse:
    item = PromptPreset(
        name=payload.name.strip(),
        description=payload.description,
        messages=[message.model_dump() for message in payload.messages],
        created_by=admin.id,
    )
    session.add(item)
    try:
        await session.flush()
        add_audit(session, admin, request, "prompt_preset.create", "prompt_preset", item.id)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError("PRESET_NAME_EXISTS", "预设名称已存在", status_code=409) from exc
    await session.refresh(item)
    return prompt_response(item)


@router.put("/prompt-presets/{preset_id}", response_model=PromptPresetResponse)
async def update_prompt_preset(
    preset_id: UUID,
    payload: PromptPresetInput,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> PromptPresetResponse:
    item = await session.get(PromptPreset, preset_id)
    if item is None:
        raise AppError("PROMPT_PRESET_NOT_FOUND", "提示词预设不存在", status_code=404)
    item.name = payload.name.strip()
    item.description = payload.description
    item.messages = [message.model_dump() for message in payload.messages]
    item.version += 1
    add_audit(session, admin, request, "prompt_preset.update", "prompt_preset", item.id)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError("PRESET_NAME_EXISTS", "预设名称已存在", status_code=409) from exc
    await session.refresh(item)
    return prompt_response(item)


@router.delete("/prompt-presets/{preset_id}", status_code=204)
async def delete_prompt_preset(
    preset_id: UUID,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> None:
    item = await session.get(PromptPreset, preset_id)
    if item is None:
        raise AppError("PROMPT_PRESET_NOT_FOUND", "提示词预设不存在", status_code=404)
    if item.is_active:
        raise AppError("PRESET_IS_ACTIVE", "请先切换到其他提示词预设", status_code=409)
    add_audit(session, admin, request, "prompt_preset.delete", "prompt_preset", item.id)
    await session.delete(item)
    await session.commit()


@router.post("/prompt-presets/{preset_id}/activate", response_model=RuntimeConfigResponse)
async def activate_prompt(
    preset_id: UUID,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> RuntimeConfigResponse:
    item = await session.get(PromptPreset, preset_id)
    if item is None:
        raise AppError("PROMPT_PRESET_NOT_FOUND", "提示词预设不存在", status_code=404)
    await activate_prompt_preset(session, item.id)
    add_audit(session, admin, request, "prompt_preset.activate", "prompt_preset", item.id)
    await session.commit()
    llm = await get_active_llm_preset(session)
    embedding = await get_active_embedding_preset(session)
    return RuntimeConfigResponse(
        llm_preset_id=llm.id if llm else None,
        prompt_preset_id=item.id,
        embedding_preset_id=embedding.id if embedding else None,
        source="database" if llm else ("environment" if settings.llm_model else "offline"),
    )


@router.get("/embedding-presets", response_model=list[EmbeddingPresetResponse])
async def list_embedding_presets(
    session: SessionDep, admin: AdminUser
) -> list[EmbeddingPresetResponse]:
    del admin
    return [
        embedding_response(item)
        for item in await session.scalars(select(EmbeddingPreset).order_by(EmbeddingPreset.name))
    ]


@router.post("/embedding-presets", response_model=EmbeddingPresetResponse, status_code=201)
async def create_embedding_preset(
    payload: EmbeddingPresetInput,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> EmbeddingPresetResponse:
    item = EmbeddingPreset(
        name=payload.name.strip(),
        provider=payload.provider,
        base_url=payload.base_url.strip().rstrip("/") if payload.base_url else None,
        api_key_ciphertext=encrypt_secret(payload.api_key),
        model=payload.model.strip(),
        dimensions=payload.dimensions,
        parameters=payload.parameters,
        created_by=admin.id,
    )
    session.add(item)
    try:
        await session.flush()
        add_audit(
            session,
            admin,
            request,
            "embedding_preset.create",
            "embedding_preset",
            item.id,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError("PRESET_NAME_EXISTS", "预设名称已存在", status_code=409) from exc
    await session.refresh(item)
    return embedding_response(item)


@router.put("/embedding-presets/{preset_id}", response_model=EmbeddingPresetResponse)
async def update_embedding_preset(
    preset_id: UUID,
    payload: EmbeddingPresetInput,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> EmbeddingPresetResponse:
    item = await session.get(EmbeddingPreset, preset_id)
    if item is None:
        raise AppError("EMBEDDING_PRESET_NOT_FOUND", "向量预设不存在", status_code=404)
    item.name = payload.name.strip()
    item.provider = payload.provider
    item.base_url = payload.base_url.strip().rstrip("/") if payload.base_url else None
    item.model = payload.model.strip()
    item.dimensions = payload.dimensions
    item.parameters = payload.parameters
    item.version += 1
    if payload.api_key:
        item.api_key_ciphertext = encrypt_secret(payload.api_key)
    add_audit(session, admin, request, "embedding_preset.update", "embedding_preset", item.id)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError("PRESET_NAME_EXISTS", "预设名称已存在", status_code=409) from exc
    await session.refresh(item)
    return embedding_response(item)


@router.delete("/embedding-presets/{preset_id}", status_code=204)
async def delete_embedding_preset(
    preset_id: UUID,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> None:
    item = await session.get(EmbeddingPreset, preset_id)
    if item is None:
        raise AppError("EMBEDDING_PRESET_NOT_FOUND", "向量预设不存在", status_code=404)
    if item.is_active:
        raise AppError("PRESET_IS_ACTIVE", "请先切换到其他向量预设", status_code=409)
    add_audit(session, admin, request, "embedding_preset.delete", "embedding_preset", item.id)
    await session.delete(item)
    await session.commit()


@router.post("/embedding-presets/{preset_id}/activate", response_model=RuntimeConfigResponse)
async def activate_embedding(
    preset_id: UUID,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> RuntimeConfigResponse:
    item = await session.get(EmbeddingPreset, preset_id)
    if item is None:
        raise AppError("EMBEDDING_PRESET_NOT_FOUND", "向量预设不存在", status_code=404)
    await activate_embedding_preset(session, item.id)
    add_audit(session, admin, request, "embedding_preset.activate", "embedding_preset", item.id)
    await session.commit()
    llm = await get_active_llm_preset(session)
    prompt = await get_active_prompt_preset(session)
    return RuntimeConfigResponse(
        llm_preset_id=llm.id if llm else None,
        prompt_preset_id=prompt.id if prompt else None,
        embedding_preset_id=item.id,
        source="database" if llm else ("environment" if settings.llm_model else "offline"),
    )


@router.post("/embedding-presets/{preset_id}/reindex", status_code=202)
async def reindex_documents(
    preset_id: UUID,
    background_tasks: BackgroundTasks,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> dict:
    item = await session.get(EmbeddingPreset, preset_id)
    if item is None:
        raise AppError("EMBEDDING_PRESET_NOT_FOUND", "向量预设不存在", status_code=404)
    if not item.is_active:
        raise AppError(
            "EMBEDDING_PRESET_NOT_ACTIVE",
            "只能使用当前激活的向量预设重建文献",
            status_code=409,
        )
    documents = list(
        await session.scalars(select(Document).where(Document.status == ProcessingStatus.SUCCEEDED))
    )
    queued: list[tuple[Document, BackgroundJob]] = []
    for document in documents:
        idempotency_key = f"document:{document.id}:embedding:{item.id}:v{item.version}"
        exists = await session.scalar(
            select(BackgroundJob.id).where(BackgroundJob.idempotency_key == idempotency_key)
        )
        if exists:
            continue
        job = BackgroundJob(
            owner_id=document.uploaded_by,
            job_type="document.reindex",
            status=ProcessingStatus.PENDING,
            progress=0,
            payload={
                "document_id": str(document.id),
                "embedding_preset_id": str(item.id),
            },
            idempotency_key=idempotency_key,
        )
        document.status = ProcessingStatus.PENDING
        session.add(job)
        queued.append((document, job))
    await session.flush()
    add_audit(
        session,
        admin,
        request,
        "embedding_preset.reindex",
        "embedding_preset",
        item.id,
        {"queued_documents": len(queued)},
    )
    await session.commit()
    for document, job in queued:
        background_tasks.add_task(process_document, document.id, job.id)
    return {"queued_documents": len(queued), "embedding_preset_id": str(item.id)}


@router.get("/runtime-config", response_model=RuntimeConfigResponse)
async def runtime_config(session: SessionDep, admin: AdminUser) -> RuntimeConfigResponse:
    del admin
    llm = await get_active_llm_preset(session)
    prompt = await get_active_prompt_preset(session)
    embedding = await get_active_embedding_preset(session)
    return RuntimeConfigResponse(
        llm_preset_id=llm.id if llm else None,
        prompt_preset_id=prompt.id if prompt else None,
        embedding_preset_id=embedding.id if embedding else None,
        source="database" if llm else ("environment" if settings.llm_model else "offline"),
    )


@router.get("/server-status", response_model=ServerStatusResponse)
async def server_status(admin: AdminUser) -> ServerStatusResponse:
    del admin
    memory = psutil.virtual_memory()
    return ServerStatusResponse(
        cpu_percent=psutil.cpu_percent(),
        memory_percent=memory.percent,
        memory_used_bytes=memory.used,
        memory_total_bytes=memory.total,
        process_rss_bytes=process.memory_info().rss,
        uptime_seconds=max(0.0, datetime.now(UTC).timestamp() - process.create_time()),
        sampled_at=datetime.now(UTC),
    )


@router.get("/application-logs", response_model=list[ApplicationLogResponse])
async def application_logs(
    admin: AdminUser,
    level: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[ApplicationLogResponse]:
    del admin
    return [ApplicationLogResponse.model_validate(item) for item in recent_logs(level, limit)]


@router.get("/sensitive-term-groups", response_model=list[SensitiveGroupResponse])
async def list_sensitive_groups(
    session: SessionDep, admin: AdminUser
) -> list[SensitiveGroupResponse]:
    del admin
    items = list(await session.scalars(select(SensitiveTerm).order_by(SensitiveTerm.term)))
    groups: dict[str, list[SensitiveTerm]] = {}
    for item in items:
        groups.setdefault(item.category, []).append(item)
    return [
        SensitiveGroupResponse(
            name=name,
            terms=[item.term for item in group],
            enabled=all(item.enabled for item in group),
            count=len(group),
        )
        for name, group in sorted(groups.items())
    ]


async def ensure_group_terms_available(
    session: SessionDep, terms: list[str], current_group: str | None = None
) -> None:
    statement = select(SensitiveTerm.term).where(SensitiveTerm.term.in_(terms))
    if current_group is not None:
        statement = statement.where(SensitiveTerm.category != current_group)
    conflicts = list(await session.scalars(statement))
    if conflicts:
        raise AppError(
            "SENSITIVE_TERM_EXISTS",
            f"以下词项已属于其他分组：{', '.join(conflicts)}",
            status_code=409,
        )


@router.post(
    "/sensitive-term-groups",
    response_model=SensitiveGroupResponse,
    status_code=201,
)
async def create_sensitive_group(
    payload: SensitiveGroupInput,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> SensitiveGroupResponse:
    name = payload.name.strip()
    exists = await session.scalar(
        select(SensitiveTerm.id).where(SensitiveTerm.category == name).limit(1)
    )
    if exists:
        raise AppError("SENSITIVE_GROUP_EXISTS", "同名敏感词分组已存在", status_code=409)
    await ensure_group_terms_available(session, payload.terms)
    session.add_all(
        [
            SensitiveTerm(
                term=term,
                category=name,
                enabled=payload.enabled,
                created_by=admin.id,
            )
            for term in payload.terms
        ]
    )
    add_audit(
        session,
        admin,
        request,
        "sensitive_group.create",
        "sensitive_group",
        name,
        {"count": len(payload.terms)},
    )
    await session.commit()
    return SensitiveGroupResponse(
        name=name, terms=payload.terms, enabled=payload.enabled, count=len(payload.terms)
    )


@router.put(
    "/sensitive-term-groups/{group_name}",
    response_model=SensitiveGroupResponse,
)
async def update_sensitive_group(
    group_name: str,
    payload: SensitiveGroupInput,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> SensitiveGroupResponse:
    existing = list(
        await session.scalars(select(SensitiveTerm).where(SensitiveTerm.category == group_name))
    )
    if not existing:
        raise AppError("SENSITIVE_GROUP_NOT_FOUND", "敏感词分组不存在", status_code=404)
    await ensure_group_terms_available(session, payload.terms, group_name)
    name = payload.name.strip()
    if name != group_name:
        duplicate_group = await session.scalar(
            select(SensitiveTerm.id).where(SensitiveTerm.category == name).limit(1)
        )
        if duplicate_group:
            raise AppError("SENSITIVE_GROUP_EXISTS", "目标分组名称已存在", status_code=409)
    await session.execute(delete(SensitiveTerm).where(SensitiveTerm.category == group_name))
    await session.flush()
    session.add_all(
        [
            SensitiveTerm(
                term=term,
                category=name,
                enabled=payload.enabled,
                created_by=admin.id,
            )
            for term in payload.terms
        ]
    )
    add_audit(
        session,
        admin,
        request,
        "sensitive_group.update",
        "sensitive_group",
        group_name,
        {"new_name": name, "count": len(payload.terms), "enabled": payload.enabled},
    )
    await session.commit()
    return SensitiveGroupResponse(
        name=name, terms=payload.terms, enabled=payload.enabled, count=len(payload.terms)
    )


@router.delete("/sensitive-term-groups/{group_name}", status_code=204)
async def delete_sensitive_group(
    group_name: str,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> None:
    count = await session.scalar(
        select(func.count(SensitiveTerm.id)).where(SensitiveTerm.category == group_name)
    )
    if not count:
        raise AppError("SENSITIVE_GROUP_NOT_FOUND", "敏感词分组不存在", status_code=404)
    await session.execute(delete(SensitiveTerm).where(SensitiveTerm.category == group_name))
    add_audit(
        session,
        admin,
        request,
        "sensitive_group.delete",
        "sensitive_group",
        group_name,
        {"count": count},
    )
    await session.commit()


@router.get("/sensitive-terms", response_model=list[SensitiveTermResponse])
async def list_sensitive_terms(
    session: SessionDep, admin: AdminUser
) -> list[SensitiveTermResponse]:
    del admin
    return [
        SensitiveTermResponse.model_validate(item, from_attributes=True)
        for item in await session.scalars(select(SensitiveTerm).order_by(SensitiveTerm.term))
    ]


@router.post("/sensitive-terms", response_model=SensitiveTermResponse, status_code=201)
async def create_sensitive_term(
    payload: SensitiveTermInput,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> SensitiveTermResponse:
    item = SensitiveTerm(
        term=payload.term.strip(),
        category=payload.category.strip(),
        enabled=payload.enabled,
        created_by=admin.id,
    )
    session.add(item)
    await session.flush()
    add_audit(session, admin, request, "sensitive_term.create", "sensitive_term", item.id)
    await session.commit()
    await session.refresh(item)
    return SensitiveTermResponse.model_validate(item, from_attributes=True)


@router.post("/sensitive-terms/import", response_model=list[SensitiveTermResponse])
async def import_sensitive_terms(
    payload: SensitiveTermImport,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> list[SensitiveTermResponse]:
    existing = set(await session.scalars(select(SensitiveTerm.term)))
    items = [
        SensitiveTerm(
            term=value.term.strip(),
            category=value.category.strip(),
            enabled=value.enabled,
            created_by=admin.id,
        )
        for value in payload.terms
        if value.term.strip() not in existing
    ]
    session.add_all(items)
    add_audit(
        session,
        admin,
        request,
        "sensitive_term.import",
        "sensitive_term",
        None,
        {"count": len(items)},
    )
    await session.commit()
    return [SensitiveTermResponse.model_validate(item, from_attributes=True) for item in items]


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def list_audit_logs(
    session: SessionDep,
    admin: AdminUser,
    action: str | None = Query(default=None, max_length=120),
    actor_user_id: UUID | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditLogResponse]:
    del admin
    statement = (
        select(AuditLog, User.display_name)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    if action:
        statement = statement.where(AuditLog.action.ilike(f"%{action.strip()}%"))
    if actor_user_id:
        statement = statement.where(AuditLog.actor_user_id == actor_user_id)
    if start_at:
        statement = statement.where(AuditLog.created_at >= start_at)
    if end_at:
        statement = statement.where(AuditLog.created_at <= end_at)
    rows = (await session.execute(statement)).all()
    return [
        AuditLogResponse(
            id=item.id,
            actor_user_id=item.actor_user_id,
            actor_display_name=display_name,
            action=item.action,
            target_type=item.target_type,
            target_id=item.target_id,
            result=item.result,
            details=item.details,
            ip_address=item.ip_address,
            created_at=item.created_at,
        )
        for item, display_name in rows
    ]


@router.get("/audit-logs/export.csv")
async def export_audit_logs(
    session: SessionDep,
    admin: AdminUser,
    action: str | None = Query(default=None, max_length=120),
    actor_user_id: UUID | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> Response:
    items = await list_audit_logs(
        session=session,
        admin=admin,
        action=action,
        actor_user_id=actor_user_id,
        start_at=start_at,
        end_at=end_at,
        limit=500,
    )
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["时间", "操作者", "动作", "对象类型", "对象 ID", "结果", "IP"])
    for item in items:
        writer.writerow(
            [
                item.created_at.isoformat(),
                item.actor_display_name or "",
                item.action,
                item.target_type,
                item.target_id or "",
                item.result,
                item.ip_address or "",
            ]
        )
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit-logs.csv"'},
    )


@router.post("/templates/{template_id}/versions", status_code=201)
async def create_template_version(
    template_id: UUID,
    payload: AdminTemplateVersionCreate,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> dict:
    template = await session.get(ReportTemplate, template_id)
    if template is None:
        raise AppError("REPORT_TEMPLATE_NOT_FOUND", "报告模板不存在", status_code=404)
    latest = await session.scalar(
        select(func.max(TemplateVersion.version)).where(TemplateVersion.template_id == template.id)
    )
    version = TemplateVersion(
        template_id=template.id,
        version=(latest or 0) + 1,
        system_prompt=payload.system_prompt,
        settings=payload.settings,
        created_by=admin.id,
    )
    session.add(version)
    await session.flush()
    session.add_all(
        [
            TemplateSection(
                template_version_id=version.id,
                key=item.key,
                title=item.title,
                position=item.position,
                instructions=item.instructions,
                required_inputs=item.required_inputs,
            )
            for item in payload.sections
        ]
    )
    template.status = TemplateStatus.PUBLISHED
    add_audit(
        session,
        admin,
        request,
        "template.version.publish",
        "report_template",
        template.id,
        {"version": version.version},
    )
    await session.commit()
    return {
        "template_id": str(template.id),
        "version_id": str(version.id),
        "version": version.version,
    }
