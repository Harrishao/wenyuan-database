from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import UserRole, UserStatus


class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: UserRole
    status: UserStatus
    document_count: int
    report_count: int
    storage_used_bytes: int = 0
    storage_quota_bytes: int | None = None
    monthly_credits: Decimal | None = None
    credit_balance: Decimal | None = None
    created_at: datetime


class AdminUserUpdate(BaseModel):
    status: UserStatus | None = None
    storage_quota_bytes: int | None = Field(default=None, ge=1_048_576)
    monthly_credits: Decimal | None = Field(default=None, ge=0)
    credit_grant: Decimal | None = Field(default=None, gt=0)


class PromptMessageInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=100_000)
    enabled: bool = True
    position: int = Field(ge=0, le=10_000)


class PromptPresetInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2_000)
    capability: str = Field(
        default="report_generation",
        min_length=2,
        max_length=40,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    variant_key: str = Field(
        default="默认风格",
        min_length=1,
        max_length=80,
    )
    messages: list[PromptMessageInput] = Field(min_length=1, max_length=100)


class PromptPresetResponse(PromptPresetInput):
    id: UUID
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PromptPresetEnabledInput(BaseModel):
    enabled: bool


class PromptCapabilityCreate(BaseModel):
    key: str = Field(
        min_length=2,
        max_length=40,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    name: str = Field(min_length=2, max_length=80)


class PromptCapabilityUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class PromptCapabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    is_system: bool
    created_at: datetime
    updated_at: datetime


class LlmPresetInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    base_url: str = Field(min_length=4, max_length=500)
    api_key: str | None = Field(default=None, max_length=2_000)
    model: str = Field(min_length=1, max_length=255)
    parameters: dict = Field(default_factory=dict)
    context_window_tokens: int = Field(default=128_000, ge=4_096)
    max_output_tokens: int = Field(default=4_096, ge=1, le=131_072)
    history_turn_limit: int = Field(default=12, ge=0, le=100)
    input_credits_per_million_tokens: Decimal = Field(default=0, ge=0)
    output_credits_per_million_tokens: Decimal = Field(default=0, ge=0)
    usage_mode: Literal["auto", "reported", "estimated"] = "auto"
    bound_prompt_preset_id: UUID | None = None
    bound_embedding_preset_id: UUID | None = None


class LlmPresetResponse(BaseModel):
    id: UUID
    name: str
    base_url: str
    model: str
    parameters: dict
    context_window_tokens: int
    max_output_tokens: int
    history_turn_limit: int
    input_credits_per_million_tokens: Decimal
    output_credits_per_million_tokens: Decimal
    usage_mode: str
    has_api_key: bool
    version: int
    is_active: bool
    bound_prompt_preset_id: UUID | None
    bound_embedding_preset_id: UUID | None
    created_at: datetime
    updated_at: datetime


class EmbeddingPresetInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    provider: Literal["local_hashing", "openai_compatible"]
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=2_000)
    model: str = Field(min_length=1, max_length=255)
    dimensions: int = Field(ge=8, le=16_000)
    parameters: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_external_provider(self) -> "EmbeddingPresetInput":
        if self.provider == "openai_compatible" and not self.base_url:
            raise ValueError("第三方向量模型必须配置 Base URL")
        return self


class EmbeddingPresetResponse(BaseModel):
    id: UUID
    name: str
    provider: str
    base_url: str | None
    model: str
    dimensions: int
    parameters: dict
    has_api_key: bool
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ActivatePresetRequest(BaseModel):
    sync_bindings: bool = True


class RuntimeConfigResponse(BaseModel):
    llm_preset_id: UUID | None
    prompt_preset_id: UUID | None
    embedding_preset_id: UUID | None
    source: Literal["database", "environment", "offline"]


class ModelListResponse(BaseModel):
    models: list[str]


class SensitiveTermInput(BaseModel):
    term: str = Field(min_length=1, max_length=255)
    category: str = Field(default="general", min_length=1, max_length=80)
    enabled: bool = True


class SensitiveTermImport(BaseModel):
    terms: list[SensitiveTermInput] = Field(min_length=1, max_length=1_000)


class SensitiveTermResponse(SensitiveTermInput):
    id: UUID
    created_at: datetime
    updated_at: datetime


class SensitiveGroupInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    terms: list[str] = Field(min_length=1, max_length=1_000)
    enabled: bool = True

    @model_validator(mode="after")
    def normalize_terms(self) -> "SensitiveGroupInput":
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("敏感词分组名称不能为空")
        normalized = list(dict.fromkeys(term.strip() for term in self.terms if term.strip()))
        if not normalized:
            raise ValueError("敏感词分组至少需要一个有效词项")
        self.terms = normalized
        return self


class SensitiveGroupResponse(SensitiveGroupInput):
    count: int


class ServerStatusResponse(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_used_bytes: int
    memory_total_bytes: int
    process_rss_bytes: int
    uptime_seconds: float
    sampled_at: datetime


class ApplicationLogResponse(BaseModel):
    timestamp: datetime
    level: str
    logger: str
    message: str
    request_id: str | None = None


class AuditLogResponse(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    actor_display_name: str | None
    action: str
    target_type: str
    target_id: str | None
    result: str
    details: dict
    ip_address: str | None
    created_at: datetime


class AdminTemplateSectionInput(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    position: int = Field(ge=1)
    instructions: str = Field(max_length=20_000)
    required_inputs: list[str] = Field(default_factory=list)


class AdminTemplateVersionCreate(BaseModel):
    system_prompt: str = Field(max_length=100_000)
    settings: dict = Field(default_factory=dict)
    sections: list[AdminTemplateSectionInput] = Field(min_length=1)
