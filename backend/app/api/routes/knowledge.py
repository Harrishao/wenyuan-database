import hashlib
from io import BytesIO
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.adapters.local_file_storage import LocalFileStorage
from app.api.dependencies import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.domain.enums import ModerationStatus, ProcessingStatus
from app.domain.models import BackgroundJob, Document, DocumentChunk, KnowledgeBase
from app.schemas.knowledge import (
    DocumentResponse,
    JobResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    SearchRequest,
    SearchResponse,
    SearchResult,
    UploadResponse,
)
from app.services.ai_config import get_runtime_embedding
from app.services.document_processing import process_document
from app.services.quotas import ensure_storage

router = APIRouter()
settings = get_settings()
storage = LocalFileStorage(settings.storage_root)
ALLOWED_TYPES: dict[str, tuple[str, set[str]]] = {
    ".pdf": ("application/pdf", {"application/pdf", "application/octet-stream"}),
    ".md": (
        "text/markdown",
        {"text/markdown", "text/plain", "application/octet-stream"},
    ),
    ".txt": ("text/plain", {"text/plain", "application/octet-stream"}),
}


async def get_owned_knowledge_base(
    session: SessionDep, knowledge_base_id: UUID, user_id: UUID
) -> KnowledgeBase:
    knowledge_base = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.user_id == user_id,
        )
    )
    if knowledge_base is None:
        raise AppError("KNOWLEDGE_BASE_NOT_FOUND", "知识库不存在", status_code=404)
    return knowledge_base


def document_response(document: Document, chunk_count: int = 0) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        original_filename=document.original_filename,
        mime_type=document.mime_type,
        file_size=document.file_size,
        status=document.status,
        summary=document.summary,
        keywords=document.keywords,
        sensitive_hits=document.sensitive_hits,
        author=document.author,
        publication_title=document.publication_title,
        publication_year=document.publication_year,
        source=document.source,
        category=document.category,
        tags=document.tags,
        moderation_status=document.moderation_status,
        moderation_note=document.moderation_note,
        error_message=document.error_message,
        chunk_count=chunk_count,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.post("", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate, session: SessionDep, current_user: CurrentUser
) -> KnowledgeBaseResponse:
    knowledge_base = KnowledgeBase(
        user_id=current_user.id,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
    )
    session.add(knowledge_base)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError("KNOWLEDGE_BASE_NAME_EXISTS", "同名知识库已存在", status_code=409) from exc
    await session.refresh(knowledge_base)
    return KnowledgeBaseResponse(
        id=knowledge_base.id,
        name=knowledge_base.name,
        description=knowledge_base.description,
        document_count=0,
        created_at=knowledge_base.created_at,
        updated_at=knowledge_base.updated_at,
    )


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    knowledge_base_id: UUID,
    payload: KnowledgeBaseUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> KnowledgeBaseResponse:
    knowledge_base = await get_owned_knowledge_base(session, knowledge_base_id, current_user.id)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise AppError("KNOWLEDGE_BASE_NAME_EMPTY", "知识库名称不能为空", status_code=422)
        knowledge_base.name = name
    if payload.description is not None:
        description = payload.description.strip()
        knowledge_base.description = description if description else None

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError("KNOWLEDGE_BASE_NAME_EXISTS", "同名知识库已存在", status_code=409) from exc
    await session.refresh(knowledge_base)

    doc_count = await session.scalar(
        select(func.count(Document.id)).where(Document.knowledge_base_id == knowledge_base.id)
    )
    return KnowledgeBaseResponse(
        id=knowledge_base.id,
        name=knowledge_base.name,
        description=knowledge_base.description,
        document_count=doc_count or 0,
        created_at=knowledge_base.created_at,
        updated_at=knowledge_base.updated_at,
    )


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    session: SessionDep, current_user: CurrentUser
) -> list[KnowledgeBaseResponse]:
    rows = (
        await session.execute(
            select(KnowledgeBase, func.count(Document.id))
            .outerjoin(Document, Document.knowledge_base_id == KnowledgeBase.id)
            .where(KnowledgeBase.user_id == current_user.id)
            .group_by(KnowledgeBase.id)
            .order_by(KnowledgeBase.updated_at.desc())
        )
    ).all()
    return [
        KnowledgeBaseResponse(
            id=item.id,
            name=item.name,
            description=item.description,
            document_count=count,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item, count in rows
    ]


@router.delete("/{knowledge_base_id}", status_code=204)
async def delete_knowledge_base(
    knowledge_base_id: UUID, session: SessionDep, current_user: CurrentUser
) -> None:
    knowledge_base = await get_owned_knowledge_base(session, knowledge_base_id, current_user.id)
    storage_keys = (
        await session.scalars(
            select(Document.storage_key).where(Document.knowledge_base_id == knowledge_base.id)
        )
    ).all()
    await session.delete(knowledge_base)
    await session.commit()
    for key in storage_keys:
        await storage.delete(key)


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    knowledge_base_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
    query: str | None = Query(default=None, max_length=200),
) -> list[DocumentResponse]:
    await get_owned_knowledge_base(session, knowledge_base_id, current_user.id)
    statement = (
        select(Document, func.count(DocumentChunk.id))
        .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
        .where(Document.knowledge_base_id == knowledge_base_id)
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
    )
    if query:
        statement = statement.where(Document.original_filename.ilike(f"%{query.strip()}%"))
    rows = (await session.execute(statement)).all()
    return [document_response(document, count) for document, count in rows]


@router.post("/{knowledge_base_id}/documents", response_model=UploadResponse, status_code=202)
async def upload_document(
    knowledge_base_id: UUID,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> UploadResponse:
    await get_owned_knowledge_base(session, knowledge_base_id, current_user.id)
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_TYPES:
        raise AppError("DOCUMENT_TYPE_UNSUPPORTED", "仅支持 PDF、Markdown 和 TXT", status_code=415)
    canonical_type, accepted_types = ALLOWED_TYPES[suffix]
    if file.content_type and file.content_type.lower() not in accepted_types:
        raise AppError(
            "DOCUMENT_MIME_MISMATCH",
            "文件声明类型与扩展名不匹配",
            status_code=415,
        )
    content = await file.read(settings.max_upload_bytes + 1)
    if not content:
        raise AppError("DOCUMENT_EMPTY", "上传文件为空", status_code=400)
    if len(content) > settings.max_upload_bytes:
        raise AppError("DOCUMENT_TOO_LARGE", "文件超过允许大小", status_code=413)
    await ensure_storage(session, current_user, len(content))
    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise AppError("DOCUMENT_CONTENT_INVALID", "PDF 文件头无效", status_code=415)
    digest = hashlib.sha256(content).hexdigest()
    duplicate = await session.scalar(
        select(Document.id).where(
            Document.knowledge_base_id == knowledge_base_id,
            Document.sha256 == digest,
        )
    )
    if duplicate:
        raise AppError("DOCUMENT_DUPLICATE", "该知识库已存在内容相同的文献", status_code=409)

    document_id = uuid4()
    storage_key = f"{current_user.id}/{knowledge_base_id}/{document_id}{suffix}"
    await storage.save(storage_key, BytesIO(content))
    document = Document(
        id=document_id,
        knowledge_base_id=knowledge_base_id,
        uploaded_by=current_user.id,
        original_filename=filename,
        storage_key=storage_key,
        mime_type=canonical_type,
        file_size=len(content),
        sha256=digest,
        status=ProcessingStatus.PENDING,
        keywords=[],
    )
    job = BackgroundJob(
        owner_id=current_user.id,
        job_type="document.process",
        status=ProcessingStatus.PENDING,
        progress=0,
        payload={"document_id": str(document_id)},
        idempotency_key=f"document:{document_id}:process:mvp1-v1",
    )
    session.add_all([document, job])
    try:
        await session.commit()
    except Exception:
        await storage.delete(storage_key)
        raise
    await session.refresh(document)
    await session.refresh(job)
    background_tasks.add_task(process_document, document.id, job.id)
    return UploadResponse(document=document_response(document), job_id=job.id)


@router.delete("/{knowledge_base_id}/documents/{document_id}", status_code=204)
async def delete_document(
    knowledge_base_id: UUID,
    document_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> None:
    await get_owned_knowledge_base(session, knowledge_base_id, current_user.id)
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.knowledge_base_id == knowledge_base_id,
        )
    )
    if document is None:
        raise AppError("DOCUMENT_NOT_FOUND", "文献不存在", status_code=404)
    storage_key = document.storage_key
    await session.delete(document)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            "DOCUMENT_DELETE_CONFLICT",
            "文献仍被其他业务数据引用，暂时无法删除",
            status_code=409,
        ) from exc
    await storage.delete(storage_key)


@router.post("/{knowledge_base_id}/documents/{document_id}/retry", response_model=JobResponse)
async def retry_document(
    knowledge_base_id: UUID,
    document_id: UUID,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    current_user: CurrentUser,
) -> JobResponse:
    await get_owned_knowledge_base(session, knowledge_base_id, current_user.id)
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.knowledge_base_id == knowledge_base_id,
        )
    )
    if document is None:
        raise AppError("DOCUMENT_NOT_FOUND", "文献不存在", status_code=404)
    document.status = ProcessingStatus.PENDING
    document.error_message = None
    job = BackgroundJob(
        owner_id=current_user.id,
        job_type="document.process",
        status=ProcessingStatus.PENDING,
        progress=0,
        payload={"document_id": str(document_id)},
        idempotency_key=f"document:{document_id}:retry:{uuid4()}",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    background_tasks.add_task(process_document, document.id, job.id)
    return JobResponse.model_validate(job, from_attributes=True)


@router.post("/{knowledge_base_id}/search", response_model=SearchResponse)
async def search_knowledge_base(
    knowledge_base_id: UUID,
    payload: SearchRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> SearchResponse:
    await get_owned_knowledge_base(session, knowledge_base_id, current_user.id)
    embedding = await get_runtime_embedding(session)
    query_vector = await embedding.embed_query(payload.query)
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    rows = (
        await session.execute(
            select(DocumentChunk, Document.original_filename, distance.label("distance"))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.knowledge_base_id == knowledge_base_id,
                Document.uploaded_by == current_user.id,
                Document.status == ProcessingStatus.SUCCEEDED,
                Document.moderation_status.in_(
                    [ModerationStatus.PENDING, ModerationStatus.APPROVED]
                ),
                DocumentChunk.embedding.is_not(None),
                DocumentChunk.embedding_model == embedding.model_name,
            )
            .order_by(distance)
            .limit(payload.top_k)
        )
    ).all()
    return SearchResponse(
        query=payload.query,
        embedding_model=embedding.model_name,
        results=[
            SearchResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_name=document_name,
                content=chunk.content,
                heading=chunk.heading,
                page_number=chunk.page_number,
                similarity=max(0.0, min(1.0, 1.0 - float(distance_value))),
            )
            for chunk, document_name, distance_value in rows
        ],
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: UUID, session: SessionDep, current_user: CurrentUser) -> JobResponse:
    job = await session.scalar(
        select(BackgroundJob).where(
            BackgroundJob.id == job_id,
            BackgroundJob.owner_id == current_user.id,
        )
    )
    if job is None:
        raise AppError("JOB_NOT_FOUND", "任务不存在", status_code=404)
    return JobResponse.model_validate(job, from_attributes=True)
