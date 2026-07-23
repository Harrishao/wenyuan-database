from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import ModerationStatus, TemplateStatus
from app.schemas.admin import AdminTemplateSectionInput


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)
    avatar_url: str | None = Field(default=None, max_length=500)
    bio: str | None = Field(default=None, max_length=500)


class UsageResponse(BaseModel):
    document_count: int
    report_count: int
    knowledge_base_count: int
    storage_bytes: int
    model_call_count: int


class AdminPasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class TemplateInput(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,79}$")
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2_000)


class TemplateVersionInput(BaseModel):
    system_prompt: str = Field(max_length=100_000)
    settings: dict = Field(default_factory=dict)
    sections: list[AdminTemplateSectionInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_sections(self) -> "TemplateVersionInput":
        keys = [section.key for section in self.sections]
        positions = [section.position for section in self.sections]
        if len(keys) != len(set(keys)) or len(positions) != len(set(positions)):
            raise ValueError("章节 key 和排序位置必须唯一")
        if sorted(positions) != list(range(1, len(positions) + 1)):
            raise ValueError("章节位置必须从 1 开始连续排列")
        top_k = self.settings.get("top_k", 4)
        if not isinstance(top_k, int) or not 1 <= top_k <= 20:
            raise ValueError("检索数量 top_k 必须在 1 到 20 之间")
        return self


class AdminTemplateVersionResponse(BaseModel):
    id: UUID
    version: int
    system_prompt: str
    settings: dict
    sections: list[AdminTemplateSectionInput]
    created_at: datetime


class AdminTemplateResponse(TemplateInput):
    id: UUID
    status: TemplateStatus
    versions: list[AdminTemplateVersionResponse]
    created_at: datetime
    updated_at: datetime


class ModerationItemResponse(BaseModel):
    content_type: Literal["document", "report"]
    content_id: UUID
    owner_id: UUID
    owner_display_name: str
    title: str
    summary: str
    hits: list[dict]
    status: ModerationStatus
    note: str | None
    created_at: datetime


class ModerationAction(BaseModel):
    status: ModerationStatus
    note: str = Field(default="", max_length=2_000)
    disable_user: bool = False
    permanent_delete: bool = False


class ReferenceMetadataUpdate(BaseModel):
    author: str | None = Field(default=None, max_length=255)
    publication_title: str | None = Field(default=None, max_length=500)
    publication_year: int | None = Field(default=None, ge=1000, le=9999)
    source: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=50)
    knowledge_base_id: UUID | None = None

    @model_validator(mode="after")
    def normalize_tags(self) -> "ReferenceMetadataUpdate":
        self.tags = list(dict.fromkeys(tag.strip() for tag in self.tags if tag.strip()))
        return self


class CitationIntegrityResponse(BaseModel):
    valid: bool
    cited_document_ids: list[UUID]
    missing_metadata_document_ids: list[UUID]
    dangling_markers: list[str]
    unused_citation_ids: list[UUID]
    warnings: list[str]


class AnnouncementInput(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    content: str = Field(min_length=1, max_length=50_000)
    pinned: bool = False
    published_at: datetime | None = None
    expires_at: datetime | None = None
    is_published: bool = False

    @model_validator(mode="after")
    def validate_window(self) -> "AnnouncementInput":
        if self.published_at and self.expires_at and self.expires_at <= self.published_at:
            raise ValueError("下线时间必须晚于发布时间")
        return self


class AnnouncementResponse(AnnouncementInput):
    id: UUID
    created_at: datetime
    updated_at: datetime
