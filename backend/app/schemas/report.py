from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import ModerationStatus, ProcessingStatus, ReportStatus


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
    sensitive_hits: list[dict]
    moderation_status: ModerationStatus
    moderation_note: str | None
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


PolishStyle = Literal["academic", "plain", "concise"]
AssistantRole = Literal["rigorous_mentor", "data_analyst"]
AssistantMode = Literal["dialogue", "revision"]


class SimilarityRunRequest(BaseModel):
    threshold: float | None = Field(default=None, ge=0, le=1)


class SimilarityMatchResponse(BaseModel):
    id: UUID
    document_chunk_id: UUID
    document_name: str
    heading: str | None
    page_number: int | None
    source_text: str
    matched_text: str
    score: float
    start_offset: int
    end_offset: int


class SimilarityJobResponse(BaseModel):
    id: UUID
    report_version: int
    status: ProcessingStatus
    overall_ratio: float
    metric_label: str = "高相似文本占比"
    parameters: dict
    matches: list[SimilarityMatchResponse]


class PolishPreviewRequest(BaseModel):
    section_key: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=2, max_length=20_000)
    style: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$",
    )


class PolishPreviewResponse(BaseModel):
    section_key: str
    style: str
    original_text: str
    polished_text: str
    model: str


class PolishAcceptRequest(PolishPreviewRequest):
    polished_text: str = Field(min_length=1, max_length=20_000)


class AssistantRequest(BaseModel):
    role: AssistantRole
    mode: AssistantMode = "dialogue"
    question: str = Field(min_length=2, max_length=4_000)
    section_key: str | None = Field(default=None, max_length=80)


class AssistantEvidenceResponse(BaseModel):
    marker: str
    document_chunk_id: UUID
    document_name: str
    content: str
    heading: str | None
    page_number: int | None


class AssistantResponse(BaseModel):
    role: AssistantRole
    mode: AssistantMode
    answer: str
    model: str
    evidence: list[AssistantEvidenceResponse]


class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=120)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ChatRecordResponse(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    capability: str
    variant_key: str
    model: str | None
    usage_estimated: bool
    created_at: datetime


class ConversationResponse(BaseModel):
    id: UUID
    report_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatRecordResponse] = Field(default_factory=list)


class ChatStreamRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8_000)
    capability: str = Field(
        default="general_chat",
        min_length=2,
        max_length=40,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    variant_key: str = Field(default="rigorous_mentor", min_length=1, max_length=80)
    section_key: str | None = Field(default=None, max_length=80)


class PromptVariantOption(BaseModel):
    key: str
    label: str


class PromptCapabilityOption(BaseModel):
    key: str
    name: str
    variants: list[PromptVariantOption]
