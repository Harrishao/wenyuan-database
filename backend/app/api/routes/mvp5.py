import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import func, or_, select

from app.adapters.local_file_storage import LocalFileStorage
from app.api.dependencies import AdminUser, CurrentUser, SessionDep
from app.api.routes.admin import add_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.domain.enums import ModerationStatus, TemplateStatus, UserStatus
from app.domain.models import (
    Announcement,
    BackgroundJob,
    Citation,
    Document,
    DocumentChunk,
    KnowledgeBase,
    Report,
    ReportSection,
    ReportTemplate,
    ReportVersion,
    TemplateSection,
    TemplateVersion,
    User,
)
from app.schemas.auth import UserResponse
from app.schemas.mvp5 import (
    AdminPasswordReset,
    AdminTemplateResponse,
    AdminTemplateVersionResponse,
    AnnouncementInput,
    AnnouncementResponse,
    CitationIntegrityResponse,
    ModerationAction,
    ModerationItemResponse,
    ProfileUpdate,
    ReferenceMetadataUpdate,
    TemplateInput,
    TemplateVersionInput,
    UsageResponse,
)

user_router = APIRouter()
admin_router = APIRouter()
public_router = APIRouter()
storage = LocalFileStorage(get_settings().storage_root)


def _version_response(
    version: TemplateVersion, sections: list[TemplateSection]
) -> AdminTemplateVersionResponse:
    return AdminTemplateVersionResponse(
        id=version.id,
        version=version.version,
        system_prompt=version.system_prompt,
        settings=version.settings,
        sections=[
            {
                "key": section.key,
                "title": section.title,
                "position": section.position,
                "instructions": section.instructions,
                "required_inputs": section.required_inputs,
            }
            for section in sorted(sections, key=lambda item: item.position)
        ],
        created_at=version.created_at,
    )


async def _template_response(
    session: SessionDep, template: ReportTemplate
) -> AdminTemplateResponse:
    versions = list(
        (
            await session.scalars(
                select(TemplateVersion)
                .where(TemplateVersion.template_id == template.id)
                .order_by(TemplateVersion.version.desc())
            )
        ).all()
    )
    version_ids = [version.id for version in versions]
    sections = (
        list(
            (
                await session.scalars(
                    select(TemplateSection).where(
                        TemplateSection.template_version_id.in_(version_ids)
                    )
                )
            ).all()
        )
        if version_ids
        else []
    )
    sections_by_version: dict[UUID, list[TemplateSection]] = {}
    for section in sections:
        sections_by_version.setdefault(section.template_version_id, []).append(section)
    return AdminTemplateResponse(
        id=template.id,
        key=template.key,
        name=template.name,
        description=template.description,
        status=template.status,
        versions=[
            _version_response(version, sections_by_version.get(version.id, []))
            for version in versions
        ],
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@user_router.patch("/profile", response_model=UserResponse)
async def update_profile(
    payload: ProfileUpdate, session: SessionDep, current_user: CurrentUser
) -> UserResponse:
    current_user.display_name = payload.display_name.strip()
    current_user.avatar_url = payload.avatar_url or None
    current_user.bio = payload.bio or None
    await session.commit()
    await session.refresh(current_user)
    return UserResponse.model_validate(current_user)


@user_router.get("/usage", response_model=UsageResponse)
async def user_usage(session: SessionDep, current_user: CurrentUser) -> UsageResponse:
    document_count, storage_bytes = (
        await session.execute(
            select(func.count(Document.id), func.coalesce(func.sum(Document.file_size), 0)).where(
                Document.uploaded_by == current_user.id
            )
        )
    ).one()
    return UsageResponse(
        document_count=document_count,
        report_count=await session.scalar(
            select(func.count(Report.id)).where(Report.owner_id == current_user.id)
        )
        or 0,
        knowledge_base_count=await session.scalar(
            select(func.count(KnowledgeBase.id)).where(KnowledgeBase.user_id == current_user.id)
        )
        or 0,
        storage_bytes=storage_bytes,
        model_call_count=await session.scalar(
            select(func.count(BackgroundJob.id)).where(
                BackgroundJob.owner_id == current_user.id,
                BackgroundJob.job_type.in_(["report_generation", "section_retry", "polish"]),
            )
        )
        or 0,
    )


@admin_router.post("/users/{user_id}/reset-password", status_code=204)
async def reset_user_password(
    user_id: UUID,
    payload: AdminPasswordReset,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> None:
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "用户不存在", status_code=404)
    user.password_hash = hash_password(payload.password)
    add_audit(session, admin, request, "user.password.reset", "user", user.id)
    await session.commit()


@admin_router.get("/templates", response_model=list[AdminTemplateResponse])
async def list_admin_templates(
    session: SessionDep, admin: AdminUser
) -> list[AdminTemplateResponse]:
    del admin
    templates = list(
        (await session.scalars(select(ReportTemplate).order_by(ReportTemplate.created_at))).all()
    )
    return [await _template_response(session, template) for template in templates]


@admin_router.post("/templates", response_model=AdminTemplateResponse, status_code=201)
async def create_template(
    payload: TemplateInput,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> AdminTemplateResponse:
    if await session.scalar(select(ReportTemplate.id).where(ReportTemplate.key == payload.key)):
        raise AppError("TEMPLATE_KEY_EXISTS", "模板标识已存在", status_code=409)
    template = ReportTemplate(
        key=payload.key,
        name=payload.name.strip(),
        description=payload.description,
        created_by=admin.id,
    )
    session.add(template)
    await session.flush()
    add_audit(session, admin, request, "template.create", "report_template", template.id)
    await session.commit()
    await session.refresh(template)
    return await _template_response(session, template)


@admin_router.put("/templates/{template_id}", response_model=AdminTemplateResponse)
async def update_template(
    template_id: UUID,
    payload: TemplateInput,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> AdminTemplateResponse:
    template = await session.get(ReportTemplate, template_id)
    if template is None:
        raise AppError("REPORT_TEMPLATE_NOT_FOUND", "报告模板不存在", status_code=404)
    duplicate = await session.scalar(
        select(ReportTemplate.id).where(
            ReportTemplate.key == payload.key, ReportTemplate.id != template.id
        )
    )
    if duplicate:
        raise AppError("TEMPLATE_KEY_EXISTS", "模板标识已存在", status_code=409)
    template.key = payload.key
    template.name = payload.name.strip()
    template.description = payload.description
    add_audit(session, admin, request, "template.update", "report_template", template.id)
    await session.commit()
    await session.refresh(template)
    return await _template_response(session, template)


@admin_router.post(
    "/templates/{template_id}/publish",
    response_model=AdminTemplateResponse,
    status_code=201,
)
async def publish_template(
    template_id: UUID,
    payload: TemplateVersionInput,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> AdminTemplateResponse:
    template = await session.get(ReportTemplate, template_id)
    if template is None:
        raise AppError("REPORT_TEMPLATE_NOT_FOUND", "报告模板不存在", status_code=404)
    latest = await session.scalar(
        select(func.max(TemplateVersion.version)).where(TemplateVersion.template_id == template.id)
    )
    settings = dict(payload.settings)
    settings["required_inputs"] = list(
        dict.fromkeys(item for section in payload.sections for item in section.required_inputs)
    )
    version = TemplateVersion(
        template_id=template.id,
        version=(latest or 0) + 1,
        system_prompt=payload.system_prompt,
        settings=settings,
        created_by=admin.id,
    )
    session.add(version)
    await session.flush()
    session.add_all(
        [
            TemplateSection(
                template_version_id=version.id,
                key=section.key,
                title=section.title,
                position=section.position,
                instructions=section.instructions,
                required_inputs=section.required_inputs,
            )
            for section in payload.sections
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
    await session.refresh(template)
    return await _template_response(session, template)


@admin_router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: UUID, request: Request, session: SessionDep, admin: AdminUser
) -> None:
    template = await session.get(ReportTemplate, template_id)
    if template is None:
        raise AppError("REPORT_TEMPLATE_NOT_FOUND", "报告模板不存在", status_code=404)
    used = await session.scalar(
        select(func.count(Report.id))
        .join(TemplateVersion, TemplateVersion.id == Report.template_version_id)
        .where(TemplateVersion.template_id == template.id)
    )
    if used:
        raise AppError(
            "TEMPLATE_IN_USE",
            "模板已有报告引用，不能删除；可保留历史版本并停止发布",
            status_code=409,
        )
    await session.delete(template)
    add_audit(session, admin, request, "template.delete", "report_template", template.id)
    await session.commit()


@admin_router.get("/moderation", response_model=list[ModerationItemResponse])
async def list_moderation_items(
    session: SessionDep,
    admin: AdminUser,
    status: ModerationStatus | None = None,
) -> list[ModerationItemResponse]:
    del admin
    documents_query = (
        select(Document, User)
        .join(User, User.id == Document.uploaded_by)
        .where(or_(func.jsonb_array_length(Document.sensitive_hits) > 0, status is not None))
    )
    versions_query = (
        select(ReportVersion, Report, User)
        .join(Report, Report.id == ReportVersion.report_id)
        .join(User, User.id == Report.owner_id)
        .where(or_(func.jsonb_array_length(ReportVersion.sensitive_hits) > 0, status is not None))
    )
    if status:
        documents_query = documents_query.where(Document.moderation_status == status)
        versions_query = versions_query.where(ReportVersion.moderation_status == status)
    result: list[ModerationItemResponse] = []
    for document, owner in (await session.execute(documents_query)).all():
        result.append(
            ModerationItemResponse(
                content_type="document",
                content_id=document.id,
                owner_id=owner.id,
                owner_display_name=owner.display_name,
                title=document.original_filename,
                summary=document.summary or "",
                hits=document.sensitive_hits,
                status=document.moderation_status,
                note=document.moderation_note,
                created_at=document.created_at,
            )
        )
    for version, report, owner in (await session.execute(versions_query)).all():
        result.append(
            ModerationItemResponse(
                content_type="report",
                content_id=version.id,
                owner_id=owner.id,
                owner_display_name=owner.display_name,
                title=f"{report.title} v{version.version}",
                summary=version.content_markdown[:300],
                hits=version.sensitive_hits,
                status=version.moderation_status,
                note=version.moderation_note,
                created_at=version.created_at,
            )
        )
    return sorted(result, key=lambda item: item.created_at, reverse=True)


@admin_router.patch(
    "/moderation/{content_type}/{content_id}", response_model=ModerationItemResponse
)
async def moderate_content(
    content_type: str,
    content_id: UUID,
    payload: ModerationAction,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> ModerationItemResponse:
    if content_type == "document":
        item = await session.get(Document, content_id)
        owner_id = item.uploaded_by if item else None
        storage_key = item.storage_key if item else None
        report_to_delete = None
    elif content_type == "report":
        item = await session.get(ReportVersion, content_id)
        report = await session.get(Report, item.report_id) if item else None
        owner_id = report.owner_id if report else None
        storage_key = None
        report_to_delete = report
    else:
        raise AppError("MODERATION_TYPE_INVALID", "不支持的审核内容类型", status_code=400)
    if item is None or owner_id is None:
        raise AppError("MODERATION_ITEM_NOT_FOUND", "审核内容不存在", status_code=404)
    item.moderation_status = payload.status
    item.moderation_note = payload.note.strip() or None
    owner = await session.get(User, owner_id)
    if payload.disable_user and owner:
        owner.status = UserStatus.DISABLED
    if payload.permanent_delete:
        await session.delete(report_to_delete if report_to_delete else item)
    add_audit(
        session,
        admin,
        request,
        "content.moderate",
        content_type,
        content_id,
        payload.model_dump(mode="json"),
    )
    await session.commit()
    if payload.permanent_delete:
        if storage_key:
            await storage.delete(storage_key)
        return ModerationItemResponse(
            content_type=content_type,
            content_id=content_id,
            owner_id=owner_id,
            owner_display_name=owner.display_name if owner else "未知用户",
            title="已彻底删除",
            summary="",
            hits=[],
            status=payload.status,
            note=payload.note,
            created_at=datetime.now(UTC),
        )
    items = await list_moderation_items(session, admin, payload.status)
    return next(item for item in items if item.content_id == content_id)


@user_router.patch("/documents/{document_id}/metadata", response_model=dict)
async def update_document_metadata(
    document_id: UUID,
    payload: ReferenceMetadataUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict:
    document = await session.scalar(
        select(Document)
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .where(Document.id == document_id, KnowledgeBase.user_id == current_user.id)
    )
    if document is None:
        raise AppError("DOCUMENT_NOT_FOUND", "文献不存在", status_code=404)
    if payload.knowledge_base_id:
        target = await session.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.id == payload.knowledge_base_id,
                KnowledgeBase.user_id == current_user.id,
            )
        )
        if target is None:
            raise AppError("KNOWLEDGE_BASE_NOT_FOUND", "目标知识库不存在", status_code=404)
        document.knowledge_base_id = target.id
    for field in ("author", "publication_title", "publication_year", "source", "category", "tags"):
        value = getattr(payload, field)
        if value is not None:
            setattr(document, field, value)
    await session.commit()
    return {"id": str(document.id), "knowledge_base_id": str(document.knowledge_base_id)}


@user_router.get(
    "/reports/{report_id}/citation-integrity", response_model=CitationIntegrityResponse
)
async def citation_integrity(
    report_id: UUID, session: SessionDep, current_user: CurrentUser
) -> CitationIntegrityResponse:
    report = await session.scalar(
        select(Report).where(Report.id == report_id, Report.owner_id == current_user.id)
    )
    if report is None:
        raise AppError("REPORT_NOT_FOUND", "报告不存在", status_code=404)
    version = await session.scalar(
        select(ReportVersion).where(
            ReportVersion.report_id == report.id,
            ReportVersion.version == report.current_version,
        )
    )
    if version is None:
        return CitationIntegrityResponse(
            valid=True,
            cited_document_ids=[],
            missing_metadata_document_ids=[],
            dangling_markers=[],
            unused_citation_ids=[],
            warnings=[],
        )
    rows = (
        await session.execute(
            select(Citation, ReportSection, Document)
            .join(ReportSection, ReportSection.id == Citation.report_section_id)
            .outerjoin(DocumentChunk, DocumentChunk.id == Citation.document_chunk_id)
            .outerjoin(Document, Document.id == DocumentChunk.document_id)
            .where(ReportSection.report_version_id == version.id)
        )
    ).all()
    dangling: set[str] = set()
    unused: list[UUID] = []
    documents: dict[UUID, Document] = {}
    for citation, section, document in rows:
        markers = set(re.findall(r"\[\d+\]", section.content_markdown))
        if citation.marker not in markers:
            unused.append(citation.id)
        if document:
            documents[document.id] = document
    for section in await session.scalars(
        select(ReportSection).where(ReportSection.report_version_id == version.id)
    ):
        stored = {
            citation.marker
            for citation, stored_section, _ in rows
            if stored_section.id == section.id
        }
        dangling.update(set(re.findall(r"\[\d+\]", section.content_markdown)) - stored)
    missing = [
        document.id
        for document in documents.values()
        if not all(
            [
                document.author,
                document.publication_title or document.original_filename,
                document.publication_year,
                document.source,
            ]
        )
    ]
    warnings = []
    if dangling:
        warnings.append("正文存在没有数据库引用记录的编号")
    if unused:
        warnings.append("数据库存在未在正文使用的引用")
    if missing:
        warnings.append("部分参考文献元数据不完整，请在导出前补充")
    return CitationIntegrityResponse(
        valid=not warnings,
        cited_document_ids=sorted(documents),
        missing_metadata_document_ids=missing,
        dangling_markers=sorted(dangling),
        unused_citation_ids=unused,
        warnings=warnings,
    )


@public_router.get("", response_model=list[AnnouncementResponse])
async def list_announcements(session: SessionDep) -> list[AnnouncementResponse]:
    now = datetime.now(UTC)
    items = (
        await session.scalars(
            select(Announcement)
            .where(
                Announcement.is_published.is_(True),
                or_(Announcement.published_at.is_(None), Announcement.published_at <= now),
                or_(Announcement.expires_at.is_(None), Announcement.expires_at > now),
            )
            .order_by(Announcement.pinned.desc(), Announcement.published_at.desc())
        )
    ).all()
    return [AnnouncementResponse.model_validate(item, from_attributes=True) for item in items]


@admin_router.get("/announcements", response_model=list[AnnouncementResponse])
async def list_admin_announcements(
    session: SessionDep, admin: AdminUser
) -> list[AnnouncementResponse]:
    del admin
    items = (
        await session.scalars(select(Announcement).order_by(Announcement.created_at.desc()))
    ).all()
    return [AnnouncementResponse.model_validate(item, from_attributes=True) for item in items]


@admin_router.post("/announcements", response_model=AnnouncementResponse, status_code=201)
async def create_announcement(
    payload: AnnouncementInput,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> AnnouncementResponse:
    item = Announcement(**payload.model_dump(), created_by=admin.id)
    session.add(item)
    await session.flush()
    add_audit(session, admin, request, "announcement.create", "announcement", item.id)
    await session.commit()
    await session.refresh(item)
    return AnnouncementResponse.model_validate(item, from_attributes=True)


@admin_router.put("/announcements/{announcement_id}", response_model=AnnouncementResponse)
async def update_announcement(
    announcement_id: UUID,
    payload: AnnouncementInput,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> AnnouncementResponse:
    item = await session.get(Announcement, announcement_id)
    if item is None:
        raise AppError("ANNOUNCEMENT_NOT_FOUND", "公告不存在", status_code=404)
    for field, value in payload.model_dump().items():
        setattr(item, field, value)
    add_audit(session, admin, request, "announcement.update", "announcement", item.id)
    await session.commit()
    await session.refresh(item)
    return AnnouncementResponse.model_validate(item, from_attributes=True)


@admin_router.delete("/announcements/{announcement_id}", status_code=204)
async def delete_announcement(
    announcement_id: UUID,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> None:
    item = await session.get(Announcement, announcement_id)
    if item is None:
        raise AppError("ANNOUNCEMENT_NOT_FOUND", "公告不存在", status_code=404)
    await session.delete(item)
    add_audit(session, admin, request, "announcement.delete", "announcement", item.id)
    await session.commit()
