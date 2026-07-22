from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import ProcessingStatus


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class KnowledgeBaseResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    document_count: int
    created_at: datetime
    updated_at: datetime


class DocumentResponse(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    original_filename: str
    mime_type: str
    file_size: int
    status: ProcessingStatus
    summary: str | None
    keywords: list[str]
    error_message: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    document: DocumentResponse
    job_id: UUID


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    top_k: int = Field(default=6, ge=1, le=20)


class SearchResult(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_name: str
    content: str
    heading: str | None
    page_number: int | None
    similarity: float


class SearchResponse(BaseModel):
    query: str
    embedding_model: str
    results: list[SearchResult]


class JobResponse(BaseModel):
    id: UUID
    job_type: str
    status: ProcessingStatus
    progress: int
    result: dict | None
    error_message: str | None
    attempts: int
    created_at: datetime
    updated_at: datetime
