import asyncio
import json
import re
from collections.abc import AsyncIterator
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.report_llm import OpenAICompatibleLlm
from app.api.dependencies import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import SessionFactory
from app.domain.enums import ModerationStatus, ProcessingStatus, ReportStatus, TemplateStatus
from app.domain.models import (
    BackgroundJob,
    Citation,
    Document,
    DocumentChunk,
    KnowledgeBase,
    Report,
    ReportSection,
    ReportTemplate,
    ReportVersion,
    SimilarityJob,
    SimilarityMatch,
    TemplateSection,
    TemplateVersion,
)
from app.schemas.report import (
    AssistantEvidenceResponse,
    AssistantRequest,
    AssistantResponse,
    CitationResponse,
    PolishAcceptRequest,
    PolishPreviewRequest,
    PolishPreviewResponse,
    ReportCreate,
    ReportCreateResponse,
    ReportDetail,
    ReportEvent,
    ReportListItem,
    ReportSectionResponse,
    ReportSectionUpdate,
    ReportTemplateResponse,
    ReportVersionResponse,
    SectionRetryRequest,
    SimilarityJobResponse,
    SimilarityMatchResponse,
    SimilarityRunRequest,
    TemplateSectionResponse,
)
from app.services.academic_tools import answer_with_evidence, polish_text
from app.services.ai_config import get_runtime_llm
from app.services.docx_export import render_report_docx
from app.services.report_generation import (
    generate_report_sections,
    rebuild_version_markdown,
    retrieve_evidence,
)
from app.services.report_templates import ensure_builtin_templates
from app.services.sensitive_scan import scan_sensitive_text
from app.services.similarity import find_similarity_candidates

templates_router = APIRouter()
reports_router = APIRouter()
settings = get_settings()


async def get_owned_report(session: AsyncSession, report_id: UUID, owner_id: UUID) -> Report:
    report = await session.scalar(
        select(Report).where(Report.id == report_id, Report.owner_id == owner_id)
    )
    if report is None:
        raise AppError("REPORT_NOT_FOUND", "报告不存在", status_code=404)
    return report


async def get_current_version(session: AsyncSession, report: Report) -> ReportVersion:
    version = await session.scalar(
        select(ReportVersion).where(
            ReportVersion.report_id == report.id,
            ReportVersion.version == report.current_version,
        )
    )
    if version is None:
        raise AppError("REPORT_VERSION_NOT_FOUND", "报告版本不存在", status_code=404)
    return version


async def get_latest_job(session: AsyncSession, report: Report) -> BackgroundJob | None:
    return await session.scalar(
        select(BackgroundJob)
        .where(
            BackgroundJob.owner_id == report.owner_id,
            BackgroundJob.job_type == "report.generate",
            BackgroundJob.payload.contains({"report_id": str(report.id)}),
        )
        .order_by(BackgroundJob.created_at.desc())
        .limit(1)
    )


def section_status(
    report: Report, job: BackgroundJob | None, section: ReportSection
) -> ProcessingStatus:
    if report.status == ReportStatus.READY:
        return ProcessingStatus.SUCCEEDED
    result = job.result if job and job.result else {}
    if section.key in result.get("completed_sections", []):
        return ProcessingStatus.SUCCEEDED
    if result.get("current_section") == section.key:
        if job and job.status != ProcessingStatus.FAILED:
            return ProcessingStatus.RUNNING
        return ProcessingStatus.FAILED
    if report.status == ReportStatus.FAILED:
        return ProcessingStatus.FAILED
    return ProcessingStatus.PENDING


async def build_report_detail(session: AsyncSession, report: Report) -> ReportDetail:
    version = await get_current_version(session, report)
    template_name = await session.scalar(
        select(ReportTemplate.name)
        .join(TemplateVersion, TemplateVersion.template_id == ReportTemplate.id)
        .where(TemplateVersion.id == report.template_version_id)
    )
    knowledge_base_name = await session.scalar(
        select(KnowledgeBase.name).where(KnowledgeBase.id == report.knowledge_base_id)
    )
    sections = (
        await session.scalars(
            select(ReportSection)
            .where(ReportSection.report_version_id == version.id)
            .order_by(ReportSection.position)
        )
    ).all()
    job = await get_latest_job(session, report)
    section_responses: list[ReportSectionResponse] = []
    for section in sections:
        citations = (
            await session.scalars(
                select(Citation)
                .where(Citation.report_section_id == section.id)
                .order_by(Citation.marker)
            )
        ).all()
        section_responses.append(
            ReportSectionResponse(
                id=section.id,
                key=section.key,
                title=section.title,
                position=section.position,
                content_markdown=section.content_markdown,
                status=section_status(report, job, section),
                citations=[
                    CitationResponse(
                        id=citation.id,
                        marker=citation.marker,
                        document_name=citation.document_name_snapshot,
                        content=citation.content_snapshot,
                        heading=citation.heading_snapshot,
                        page_number=citation.page_number_snapshot,
                    )
                    for citation in citations
                ],
            )
        )
    return ReportDetail(
        id=report.id,
        title=report.title,
        status=report.status,
        template_name=template_name or "未知模板",
        knowledge_base_name=knowledge_base_name or "已删除知识库",
        current_version=report.current_version,
        created_at=report.created_at,
        updated_at=report.updated_at,
        inputs=dict(version.generation_context.get("inputs", {})),
        progress=job.progress if job else (100 if report.status == ReportStatus.READY else 0),
        sensitive_hits=version.sensitive_hits,
        moderation_status=version.moderation_status,
        moderation_note=version.moderation_note,
        sections=section_responses,
    )


async def snapshot_version(
    session: AsyncSession,
    report: Report,
    source: ReportVersion,
    reason: str,
    content_override: tuple[str, str] | None = None,
) -> ReportVersion:
    new_version = ReportVersion(
        report_id=report.id,
        version=report.current_version + 1,
        content_markdown=source.content_markdown,
        generation_context=dict(source.generation_context),
        sensitive_hits=list(source.sensitive_hits),
        reason=reason,
        created_by=report.owner_id,
    )
    session.add(new_version)
    await session.flush()
    old_sections = (
        await session.scalars(
            select(ReportSection)
            .where(ReportSection.report_version_id == source.id)
            .order_by(ReportSection.position)
        )
    ).all()
    for old_section in old_sections:
        content = old_section.content_markdown
        if content_override and old_section.key == content_override[0]:
            content = content_override[1]
        new_section = ReportSection(
            report_version_id=new_version.id,
            key=old_section.key,
            title=old_section.title,
            position=old_section.position,
            content_markdown=content,
        )
        session.add(new_section)
        await session.flush()
        citations = list(
            await session.scalars(
                select(Citation).where(Citation.report_section_id == old_section.id)
            )
        )
        citations_by_marker = {citation.marker: citation for citation in citations}
        referenced_markers = set(re.findall(r"\[\d+\]", content))
        missing_markers = referenced_markers - citations_by_marker.keys()
        if missing_markers:
            historical_citations = list(
                await session.scalars(
                    select(Citation)
                    .join(ReportSection, ReportSection.id == Citation.report_section_id)
                    .join(ReportVersion, ReportVersion.id == ReportSection.report_version_id)
                    .where(
                        ReportVersion.report_id == report.id,
                        ReportSection.key == old_section.key,
                        Citation.marker.in_(missing_markers),
                    )
                    .order_by(ReportVersion.version.desc())
                )
            )
            for citation in historical_citations:
                citations_by_marker.setdefault(citation.marker, citation)
        session.add_all(
            [
                Citation(
                    report_section_id=new_section.id,
                    document_chunk_id=citation.document_chunk_id,
                    marker=citation.marker,
                    document_name_snapshot=citation.document_name_snapshot,
                    content_snapshot=citation.content_snapshot,
                    heading_snapshot=citation.heading_snapshot,
                    page_number_snapshot=citation.page_number_snapshot,
                )
                for citation in citations_by_marker.values()
            ]
        )
    report.current_version = new_version.version
    await rebuild_version_markdown(session, new_version)
    new_version.sensitive_hits = await scan_sensitive_text(session, new_version.content_markdown)
    new_version.moderation_status = (
        ModerationStatus.PENDING if new_version.sensitive_hits else ModerationStatus.APPROVED
    )
    return new_version


@templates_router.get("", response_model=list[ReportTemplateResponse])
async def list_report_templates(
    session: SessionDep, current_user: CurrentUser
) -> list[ReportTemplateResponse]:
    del current_user
    await ensure_builtin_templates(session)
    templates = (
        await session.scalars(
            select(ReportTemplate)
            .where(ReportTemplate.status == TemplateStatus.PUBLISHED)
            .order_by(ReportTemplate.name)
        )
    ).all()
    responses = []
    for template in templates:
        version = await session.scalar(
            select(TemplateVersion)
            .where(TemplateVersion.template_id == template.id)
            .order_by(TemplateVersion.version.desc())
            .limit(1)
        )
        if version is None:
            continue
        sections = (
            await session.scalars(
                select(TemplateSection)
                .where(TemplateSection.template_version_id == version.id)
                .order_by(TemplateSection.position)
            )
        ).all()
        responses.append(
            ReportTemplateResponse(
                id=template.id,
                key=template.key,
                name=template.name,
                description=template.description,
                version_id=version.id,
                version=version.version,
                required_inputs=list(version.settings.get("required_inputs", [])),
                sections=[
                    TemplateSectionResponse(
                        key=item.key,
                        title=item.title,
                        position=item.position,
                        instructions=item.instructions,
                        required_inputs=item.required_inputs,
                    )
                    for item in sections
                ],
            )
        )
    return responses


@reports_router.post("", response_model=ReportCreateResponse, status_code=202)
async def create_report(
    payload: ReportCreate,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    current_user: CurrentUser,
) -> ReportCreateResponse:
    await ensure_builtin_templates(session)
    knowledge_base = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == payload.knowledge_base_id,
            KnowledgeBase.user_id == current_user.id,
        )
    )
    if knowledge_base is None:
        raise AppError("KNOWLEDGE_BASE_NOT_FOUND", "知识库不存在", status_code=404)
    document_count = await session.scalar(
        select(func.count(Document.id)).where(
            Document.knowledge_base_id == knowledge_base.id,
            Document.status == ProcessingStatus.SUCCEEDED,
        )
    )
    if (document_count or 0) < 2:
        raise AppError(
            "REPORT_EVIDENCE_INSUFFICIENT",
            "至少需要两篇处理成功的文献",
            status_code=409,
        )
    template = await session.scalar(
        select(ReportTemplate).where(
            ReportTemplate.key == payload.template_key,
            ReportTemplate.status == TemplateStatus.PUBLISHED,
        )
    )
    if template is None:
        raise AppError("REPORT_TEMPLATE_NOT_FOUND", "报告模板不存在", status_code=404)
    template_version = await session.scalar(
        select(TemplateVersion)
        .where(TemplateVersion.template_id == template.id)
        .order_by(TemplateVersion.version.desc())
        .limit(1)
    )
    if template_version is None:
        raise AppError("REPORT_TEMPLATE_INVALID", "报告模板没有可用版本", status_code=409)
    required_inputs = list(template_version.settings.get("required_inputs", []))
    missing = [key for key in required_inputs if not payload.inputs.get(key, "").strip()]
    if missing:
        raise AppError(
            "REPORT_INPUT_MISSING",
            f"缺少必填字段：{', '.join(missing)}",
            status_code=422,
        )
    template_sections = (
        await session.scalars(
            select(TemplateSection)
            .where(TemplateSection.template_version_id == template_version.id)
            .order_by(TemplateSection.position)
        )
    ).all()
    report = Report(
        owner_id=current_user.id,
        knowledge_base_id=knowledge_base.id,
        template_version_id=template_version.id,
        title=payload.title.strip(),
        status=ReportStatus.DRAFT,
        current_version=1,
    )
    session.add(report)
    await session.flush()
    version = ReportVersion(
        report_id=report.id,
        version=1,
        content_markdown="",
        generation_context={
            "inputs": {key: value.strip() for key, value in payload.inputs.items()},
            "template_key": template.key,
            "template_version": template_version.version,
        },
        reason="initial_generation",
        created_by=current_user.id,
    )
    session.add(version)
    await session.flush()
    session.add_all(
        [
            ReportSection(
                report_version_id=version.id,
                key=item.key,
                title=item.title,
                position=item.position,
                content_markdown="",
            )
            for item in template_sections
        ]
    )
    job = BackgroundJob(
        owner_id=current_user.id,
        job_type="report.generate",
        status=ProcessingStatus.PENDING,
        progress=0,
        payload={"report_id": str(report.id), "section_keys": None},
        idempotency_key=f"report:{report.id}:generate:v1",
    )
    session.add(job)
    await session.commit()
    await session.refresh(report)
    await session.refresh(job)
    background_tasks.add_task(generate_report_sections, report.id, job.id)
    return ReportCreateResponse(report=await build_report_detail(session, report), job_id=job.id)


@reports_router.get("", response_model=list[ReportListItem])
async def list_reports(
    session: SessionDep,
    current_user: CurrentUser,
    query: str | None = Query(default=None, max_length=200),
) -> list[ReportListItem]:
    statement = (
        select(Report, ReportTemplate.name, KnowledgeBase.name)
        .join(TemplateVersion, TemplateVersion.id == Report.template_version_id)
        .join(ReportTemplate, ReportTemplate.id == TemplateVersion.template_id)
        .join(KnowledgeBase, KnowledgeBase.id == Report.knowledge_base_id)
        .where(Report.owner_id == current_user.id)
        .order_by(Report.updated_at.desc())
    )
    if query:
        search_term = f"%{query.strip()}%"
        statement = statement.where(
            or_(Report.title.ilike(search_term), ReportTemplate.name.ilike(search_term))
        )
    rows = (await session.execute(statement)).all()
    return [
        ReportListItem(
            id=report.id,
            title=report.title,
            status=report.status,
            template_name=template_name,
            knowledge_base_name=knowledge_base_name,
            current_version=report.current_version,
            created_at=report.created_at,
            updated_at=report.updated_at,
        )
        for report, template_name, knowledge_base_name in rows
    ]


@reports_router.get("/{report_id}", response_model=ReportDetail)
async def get_report(
    report_id: UUID, session: SessionDep, current_user: CurrentUser
) -> ReportDetail:
    report = await get_owned_report(session, report_id, current_user.id)
    return await build_report_detail(session, report)


@reports_router.delete("/{report_id}", status_code=204)
async def delete_report(report_id: UUID, session: SessionDep, current_user: CurrentUser) -> None:
    report = await get_owned_report(session, report_id, current_user.id)
    await session.delete(report)
    await session.commit()


@reports_router.patch("/{report_id}/sections/{section_key}", response_model=ReportDetail)
async def update_report_section(
    report_id: UUID,
    section_key: str,
    payload: ReportSectionUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ReportDetail:
    report = await get_owned_report(session, report_id, current_user.id)
    source = await get_current_version(session, report)
    exists = await session.scalar(
        select(ReportSection.id).where(
            ReportSection.report_version_id == source.id,
            ReportSection.key == section_key,
        )
    )
    if exists is None:
        raise AppError("REPORT_SECTION_NOT_FOUND", "报告章节不存在", status_code=404)
    await snapshot_version(
        session,
        report,
        source,
        "auto_save",
        (section_key, payload.content_markdown.strip()),
    )
    report.status = ReportStatus.READY
    await session.commit()
    await session.refresh(report)
    return await build_report_detail(session, report)


@reports_router.post(
    "/{report_id}/sections/{section_key}/retry", response_model=ReportCreateResponse
)
async def retry_report_section(
    report_id: UUID,
    section_key: str,
    payload: SectionRetryRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    current_user: CurrentUser,
) -> ReportCreateResponse:
    report = await get_owned_report(session, report_id, current_user.id)
    source = await get_current_version(session, report)
    exists = await session.scalar(
        select(ReportSection.id).where(
            ReportSection.report_version_id == source.id,
            ReportSection.key == section_key,
        )
    )
    if exists is None:
        raise AppError("REPORT_SECTION_NOT_FOUND", "报告章节不存在", status_code=404)
    await snapshot_version(session, report, source, payload.reason)
    job = BackgroundJob(
        owner_id=current_user.id,
        job_type="report.generate",
        status=ProcessingStatus.PENDING,
        progress=0,
        payload={"report_id": str(report.id), "section_keys": [section_key]},
        idempotency_key=f"report:{report.id}:section:{section_key}:version:{report.current_version}",
    )
    session.add(job)
    await session.commit()
    await session.refresh(report)
    await session.refresh(job)
    background_tasks.add_task(generate_report_sections, report.id, job.id, [section_key])
    return ReportCreateResponse(report=await build_report_detail(session, report), job_id=job.id)


@reports_router.get("/{report_id}/versions", response_model=list[ReportVersionResponse])
async def list_report_versions(
    report_id: UUID, session: SessionDep, current_user: CurrentUser
) -> list[ReportVersionResponse]:
    report = await get_owned_report(session, report_id, current_user.id)
    versions = (
        await session.scalars(
            select(ReportVersion)
            .where(ReportVersion.report_id == report.id)
            .order_by(ReportVersion.version.desc())
        )
    ).all()
    return [
        ReportVersionResponse(
            id=item.id,
            version=item.version,
            reason=item.reason,
            content_markdown=item.content_markdown,
            created_at=item.created_at,
        )
        for item in versions
    ]


@reports_router.post("/{report_id}/versions/{version_number}/restore", response_model=ReportDetail)
async def restore_report_version(
    report_id: UUID,
    version_number: int,
    session: SessionDep,
    current_user: CurrentUser,
) -> ReportDetail:
    report = await get_owned_report(session, report_id, current_user.id)
    source = await session.scalar(
        select(ReportVersion).where(
            ReportVersion.report_id == report.id,
            ReportVersion.version == version_number,
        )
    )
    if source is None:
        raise AppError("REPORT_VERSION_NOT_FOUND", "报告版本不存在", status_code=404)
    await snapshot_version(session, report, source, f"restore_v{version_number}")
    report.status = ReportStatus.READY
    await session.commit()
    await session.refresh(report)
    return await build_report_detail(session, report)


@reports_router.get("/{report_id}/export.docx")
async def export_report_docx(
    report_id: UUID, session: SessionDep, current_user: CurrentUser
) -> StreamingResponse:
    report = await get_owned_report(session, report_id, current_user.id)
    version = await get_current_version(session, report)
    if version.moderation_status in {
        ModerationStatus.RESTRICTED,
        ModerationStatus.REMOVED,
    }:
        raise AppError(
            "REPORT_CONTENT_RESTRICTED",
            "当前报告版本已被限制或下架，不能导出",
            status_code=403,
        )
    sections = list(
        await session.scalars(
            select(ReportSection)
            .where(ReportSection.report_version_id == version.id)
            .order_by(ReportSection.position)
        )
    )
    citation_rows = (
        await session.execute(
            select(Citation, ReportSection, Document)
            .join(ReportSection, ReportSection.id == Citation.report_section_id)
            .join(DocumentChunk, DocumentChunk.id == Citation.document_chunk_id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(ReportSection.report_version_id == version.id)
            .order_by(ReportSection.position, Citation.marker)
        )
    ).all()
    citation_count = await session.scalar(
        select(func.count(Citation.id))
        .join(ReportSection, ReportSection.id == Citation.report_section_id)
        .where(ReportSection.report_version_id == version.id)
    )
    if (citation_count or 0) != len(citation_rows):
        raise AppError(
            "REFERENCE_SOURCE_UNAVAILABLE",
            "部分引用的原始文献已删除，无法生成一一对应的参考文献列表",
            status_code=409,
        )
    references: list[Document] = []
    reference_numbers: dict[UUID, int] = {}
    citation_numbers: dict[UUID, dict[str, int]] = {}
    for citation, section, document in citation_rows:
        number = reference_numbers.get(document.id)
        if number is None:
            references.append(document)
            number = len(references)
            reference_numbers[document.id] = number
        citation_numbers.setdefault(section.id, {})[citation.marker] = number
    missing = [
        item.original_filename
        for item in references
        if not all(
            [
                item.author,
                item.publication_title or item.original_filename,
                item.publication_year,
                item.source,
            ]
        )
    ]
    if missing:
        raise AppError(
            "REFERENCE_METADATA_INCOMPLETE",
            "参考文献元数据不完整，导出前请补充作者、年份和来源",
            status_code=409,
            details={"documents": missing},
        )
    payload = render_report_docx(report, sections, references, citation_numbers)
    filename = f"report-{report.id}.docx"
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@reports_router.get("/{report_id}/events")
async def stream_report_events(
    report_id: UUID, session: SessionDep, current_user: CurrentUser
) -> StreamingResponse:
    await get_owned_report(session, report_id, current_user.id)
    owner_id = current_user.id

    async def events() -> AsyncIterator[str]:
        previous = ""
        for _ in range(600):
            async with SessionFactory() as stream_session:
                report = await stream_session.scalar(
                    select(Report).where(Report.id == report_id, Report.owner_id == owner_id)
                )
                if report is None:
                    return
                job = await get_latest_job(stream_session, report)
                result = job.result if job and job.result else {}
                event = ReportEvent(
                    report_id=report.id,
                    report_status=report.status,
                    job_status=job.status if job else None,
                    progress=job.progress if job else 0,
                    current_section=result.get("current_section"),
                    completed_sections=result.get("completed_sections", []),
                    error_message=job.error_message if job else None,
                )
                serialized = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
                if serialized != previous:
                    yield f"event: progress\ndata: {serialized}\n\n"
                    previous = serialized
                if report.status in {ReportStatus.READY, ReportStatus.FAILED}:
                    yield "event: complete\ndata: {}\n\n"
                    return
            await asyncio.sleep(0.75)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@reports_router.post("/{report_id}/similarity", response_model=SimilarityJobResponse)
async def run_report_similarity(
    report_id: UUID,
    payload: SimilarityRunRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> SimilarityJobResponse:
    report = await get_owned_report(session, report_id, current_user.id)
    version = await get_current_version(session, report)
    threshold = (
        payload.threshold if payload.threshold is not None else settings.similarity_threshold
    )
    chunk_rows = list(
        (
            await session.execute(
                select(DocumentChunk, Document.original_filename)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(
                    Document.knowledge_base_id == report.knowledge_base_id,
                    Document.uploaded_by == current_user.id,
                    Document.status == ProcessingStatus.SUCCEEDED,
                )
                .order_by(Document.original_filename, DocumentChunk.position)
            )
        ).all()
    )
    parameters = {
        "algorithm": "tfidf_char_cosine",
        "threshold": threshold,
        "ngram_range": [settings.similarity_ngram_min, settings.similarity_ngram_max],
        "min_sentence_chars": settings.similarity_min_sentence_chars,
    }
    job = SimilarityJob(
        owner_id=current_user.id,
        report_version_id=version.id,
        status=ProcessingStatus.RUNNING,
        parameters=parameters,
    )
    session.add(job)
    await session.flush()
    candidates, ratio = find_similarity_candidates(
        version.content_markdown,
        [chunk.content for chunk, _ in chunk_rows],
        threshold=threshold,
        ngram_range=(settings.similarity_ngram_min, settings.similarity_ngram_max),
        min_sentence_chars=settings.similarity_min_sentence_chars,
    )
    matches: list[SimilarityMatch] = []
    for candidate in candidates:
        chunk, _ = chunk_rows[candidate.candidate_index]
        match = SimilarityMatch(
            job_id=job.id,
            document_chunk_id=chunk.id,
            source_text=candidate.source.text,
            matched_text=chunk.content,
            score=Decimal(f"{candidate.score:.5f}"),
            start_offset=candidate.source.start_offset,
            end_offset=candidate.source.end_offset,
        )
        session.add(match)
        matches.append(match)
    job.overall_ratio = Decimal(f"{ratio:.5f}")
    job.status = ProcessingStatus.SUCCEEDED
    await session.commit()
    for match in matches:
        await session.refresh(match)
    document_names = {chunk.id: name for chunk, name in chunk_rows}
    chunks = {chunk.id: chunk for chunk, _ in chunk_rows}
    return SimilarityJobResponse(
        id=job.id,
        report_version=version.version,
        status=job.status,
        overall_ratio=float(job.overall_ratio or 0),
        parameters=parameters,
        matches=[
            SimilarityMatchResponse(
                id=match.id,
                document_chunk_id=match.document_chunk_id,
                document_name=document_names[match.document_chunk_id],
                heading=chunks[match.document_chunk_id].heading,
                page_number=chunks[match.document_chunk_id].page_number,
                source_text=match.source_text,
                matched_text=match.matched_text,
                score=float(match.score),
                start_offset=match.start_offset,
                end_offset=match.end_offset,
            )
            for match in matches
        ],
    )


@reports_router.post("/{report_id}/polish", response_model=PolishPreviewResponse)
async def preview_report_polish(
    report_id: UUID,
    payload: PolishPreviewRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> PolishPreviewResponse:
    report = await get_owned_report(session, report_id, current_user.id)
    version = await get_current_version(session, report)
    section = await session.scalar(
        select(ReportSection).where(
            ReportSection.report_version_id == version.id,
            ReportSection.key == payload.section_key,
        )
    )
    if section is None:
        raise AppError("REPORT_SECTION_NOT_FOUND", "报告章节不存在", status_code=404)
    if payload.text not in section.content_markdown:
        raise AppError(
            "POLISH_SOURCE_STALE",
            "待润色文字已不在当前章节中，请重新选择",
            status_code=409,
        )
    runtime_llm = await get_runtime_llm(session)
    polished, model = await polish_text(
        payload.text,
        payload.style,
        runtime_llm if isinstance(runtime_llm, OpenAICompatibleLlm) else None,
    )
    return PolishPreviewResponse(
        section_key=payload.section_key,
        style=payload.style,
        original_text=payload.text,
        polished_text=polished,
        model=model,
    )


@reports_router.post("/{report_id}/polish/accept", response_model=ReportDetail)
async def accept_report_polish(
    report_id: UUID,
    payload: PolishAcceptRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> ReportDetail:
    report = await get_owned_report(session, report_id, current_user.id)
    version = await get_current_version(session, report)
    section = await session.scalar(
        select(ReportSection).where(
            ReportSection.report_version_id == version.id,
            ReportSection.key == payload.section_key,
        )
    )
    if section is None:
        raise AppError("REPORT_SECTION_NOT_FOUND", "报告章节不存在", status_code=404)
    if payload.text not in section.content_markdown:
        raise AppError(
            "POLISH_SOURCE_STALE",
            "原文已变化，润色结果未写入",
            status_code=409,
        )
    replacement = section.content_markdown.replace(payload.text, payload.polished_text, 1)
    await snapshot_version(
        session,
        report,
        version,
        f"polish_{payload.style}",
        (section.key, replacement),
    )
    report.status = ReportStatus.READY
    await session.commit()
    await session.refresh(report)
    return await build_report_detail(session, report)


@reports_router.post("/{report_id}/assistant", response_model=AssistantResponse)
async def ask_report_assistant(
    report_id: UUID,
    payload: AssistantRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> AssistantResponse:
    report = await get_owned_report(session, report_id, current_user.id)
    version = await get_current_version(session, report)
    context = version.content_markdown
    if payload.section_key:
        section = await session.scalar(
            select(ReportSection).where(
                ReportSection.report_version_id == version.id,
                ReportSection.key == payload.section_key,
            )
        )
        if section is None:
            raise AppError("REPORT_SECTION_NOT_FOUND", "报告章节不存在", status_code=404)
        context = section.content_markdown
    evidence_rows = await retrieve_evidence(
        session,
        report,
        f"{report.title} {payload.question} {context[:800]}",
        4,
    )
    evidence_payload = [
        {
            "marker": index,
            "document": document_name,
            "heading": chunk.heading,
            "page_number": chunk.page_number,
            "content": chunk.content,
            "similarity": similarity,
        }
        for index, (chunk, document_name, similarity) in enumerate(evidence_rows, start=1)
    ]
    runtime_llm = await get_runtime_llm(session)
    answer, markers, model = await answer_with_evidence(
        role=payload.role,
        mode=payload.mode,
        question=payload.question,
        report_context=context,
        evidence=evidence_payload,
        llm=runtime_llm if isinstance(runtime_llm, OpenAICompatibleLlm) else None,
    )
    return AssistantResponse(
        role=payload.role,
        mode=payload.mode,
        answer=answer,
        model=model,
        evidence=[
            AssistantEvidenceResponse(
                marker=f"[{marker}]",
                document_chunk_id=evidence_rows[marker - 1][0].id,
                document_name=evidence_rows[marker - 1][1],
                content=evidence_rows[marker - 1][0].content,
                heading=evidence_rows[marker - 1][0].heading,
                page_number=evidence_rows[marker - 1][0].page_number,
            )
            for marker in markers
        ],
    )
