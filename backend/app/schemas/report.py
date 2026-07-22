from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import ProcessingStatus, ReportStatus


class TemplateSectionResponse(BaseModel):
    key: str
    title: str
    position: int
    instructions: str
    required_inputs: list[str]


class ReportTemplateResponse(BaseModel):
    id: UUID
    key: str
    name: str
    description: str | None
    version_id: UUID
    version: int
    required_inputs: list[str]
    sections: list[TemplateSectionResponse]


class ReportCreate(BaseModel):
    knowledge_base_id: UUID
    template_key: str
    title: str = Field(min_length=2, max_length=255)
    inputs: dict[str, str] = Field(default_factory=dict)


class CitationResponse(BaseModel):
    id: UUID
    marker: str
    document_name: str
    content: str
    heading: str | None
    page_number: int | None


class ReportSectionResponse(BaseModel):
    id: UUID
    key: str
    title: str
    position: int
    content_markdown: str
    status: ProcessingStatus
    citations: list[CitationResponse]


class ReportListItem(BaseModel):
    id: UUID
    title: str
    status: ReportStatus
    template_name: str
    knowledge_base_name: str
    current_version: int
    created_at: datetime
    updated_at: datetime


class ReportDetail(ReportListItem):
    inputs: dict[str, str]
    progress: int
    sections: list[ReportSectionResponse]


class ReportCreateResponse(BaseModel):
    report: ReportDetail
    job_id: UUID


class ReportSectionUpdate(BaseModel):
    content_markdown: str = Field(max_length=200_000)


class ReportVersionResponse(BaseModel):
    id: UUID
    version: int
    reason: str
    content_markdown: str
    created_at: datetime


class SectionRetryRequest(BaseModel):
    reason: str = Field(default="generation_retry", max_length=80)


class ReportEvent(BaseModel):
    report_id: UUID
    report_status: ReportStatus
    job_status: ProcessingStatus | None
    progress: int
    current_section: str | None = None
    completed_sections: list[str] = Field(default_factory=list)
    error_message: str | None = None


class ReportInputValidation(BaseModel):
    required_inputs: list[str]
    inputs: dict[str, str]

    @model_validator(mode="after")
    def ensure_required_inputs(self) -> "ReportInputValidation":
        missing = [key for key in self.required_inputs if not self.inputs.get(key, "").strip()]
        if missing:
            raise ValueError(f"缺少必填字段：{', '.join(missing)}")
        return self
