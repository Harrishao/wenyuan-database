from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.enums import (
    ProcessingStatus,
    ReportStatus,
    TemplateStatus,
    UserRole,
    UserStatus,
)

EMBEDDING_DIMENSIONS = 512


class UuidPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(80))
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=UserRole.STUDENT,
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(
            UserStatus,
            name="user_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=UserStatus.ACTIVE,
    )


class RefreshToken(UuidPrimaryKeyMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class KnowledgeBase(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_bases"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_knowledge_bases_user_name"),)


class Document(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    knowledge_base_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    uploaded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str] = mapped_column(String(120))
    file_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(
            ProcessingStatus,
            name="processing_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ProcessingStatus.PENDING,
        index=True,
    )
    summary: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
    parser_version: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "sha256", name="uq_documents_knowledge_base_sha256"),
    )


class DocumentChunk(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_chunks"

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    heading: Mapped[str | None] = mapped_column(String(500))
    page_number: Mapped[int | None] = mapped_column(Integer)
    char_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    processing_version: Mapped[str] = mapped_column(String(80), default="v1")
    __table_args__ = (
        UniqueConstraint("document_id", "position", name="uq_document_chunks_document_position"),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class ReportTemplate(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "report_templates"

    key: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[TemplateStatus] = mapped_column(
        Enum(
            TemplateStatus,
            name="template_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=TemplateStatus.DRAFT,
    )


class TemplateVersion(UuidPrimaryKeyMixin, Base):
    __tablename__ = "template_versions"

    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("report_templates.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    system_prompt: Mapped[str] = mapped_column(Text)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_template_versions_template_version"),
    )


class TemplateSection(UuidPrimaryKeyMixin, Base):
    __tablename__ = "template_sections"

    template_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("template_versions.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    instructions: Mapped[str] = mapped_column(Text)
    required_inputs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    __table_args__ = (
        UniqueConstraint("template_version_id", "key", name="uq_template_sections_version_key"),
        UniqueConstraint(
            "template_version_id", "position", name="uq_template_sections_version_position"
        ),
    )


class Report(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reports"

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    knowledge_base_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    template_version_id: Mapped[UUID] = mapped_column(ForeignKey("template_versions.id"))
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[ReportStatus] = mapped_column(
        Enum(
            ReportStatus,
            name="report_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ReportStatus.DRAFT,
        index=True,
    )
    current_version: Mapped[int] = mapped_column(Integer, default=0)


class ReportVersion(UuidPrimaryKeyMixin, Base):
    __tablename__ = "report_versions"

    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    content_markdown: Mapped[str] = mapped_column(Text)
    generation_context: Mapped[dict] = mapped_column(JSONB, default=dict)
    reason: Mapped[str] = mapped_column(String(80), default="manual_save")
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint("report_id", "version", name="uq_report_versions_report_version"),
    )


class ReportSection(UuidPrimaryKeyMixin, Base):
    __tablename__ = "report_sections"

    report_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("report_versions.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    content_markdown: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("report_version_id", "key", name="uq_report_sections_version_key"),
        UniqueConstraint(
            "report_version_id", "position", name="uq_report_sections_version_position"
        ),
    )


class Citation(UuidPrimaryKeyMixin, Base):
    __tablename__ = "citations"

    report_section_id: Mapped[UUID] = mapped_column(
        ForeignKey("report_sections.id", ondelete="CASCADE"), index=True
    )
    document_chunk_id: Mapped[UUID] = mapped_column(ForeignKey("document_chunks.id"), index=True)
    marker: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint("report_section_id", "marker", name="uq_citations_section_marker"),
    )


class SimilarityJob(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "similarity_jobs"

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    report_version_id: Mapped[UUID] = mapped_column(ForeignKey("report_versions.id"), index=True)
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(
            ProcessingStatus,
            name="similarity_job_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ProcessingStatus.PENDING,
    )
    overall_ratio: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)


class SimilarityMatch(UuidPrimaryKeyMixin, Base):
    __tablename__ = "similarity_matches"

    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("similarity_jobs.id", ondelete="CASCADE"), index=True
    )
    document_chunk_id: Mapped[UUID] = mapped_column(ForeignKey("document_chunks.id"), index=True)
    source_text: Mapped[str] = mapped_column(Text)
    matched_text: Mapped[str] = mapped_column(Text)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 5))
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)


class BackgroundJob(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "background_jobs"

    owner_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    job_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(
            ProcessingStatus,
            name="background_job_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ProcessingStatus.PENDING,
        index=True,
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)


class SensitiveTerm(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sensitive_terms"

    term: Mapped[str] = mapped_column(String(255), unique=True)
    category: Mapped[str] = mapped_column(String(80), default="general")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AuditLog(UuidPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"

    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[str | None] = mapped_column(String(80))
    result: Mapped[str] = mapped_column(String(40))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
