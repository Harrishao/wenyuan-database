from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "文渊 API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    log_level: str = "INFO"
    app_port: int = Field(default=4396, ge=1, le=65_535)
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://wenyuan:wenyuan@localhost:5432/wenyuan"
    cors_origins: str = "http://localhost:7777"
    storage_root: Path = Path("./data/uploads")
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    chunk_target_chars: int = Field(default=650, ge=100, le=4000)
    chunk_overlap_chars: int = Field(default=100, ge=0, le=1000)

    jwt_secret: SecretStr = SecretStr("change-this-development-secret-before-production")
    access_token_minutes: int = Field(default=30, gt=0)
    refresh_token_days: int = Field(default=7, gt=0)
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65_535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    smtp_use_tls: bool = True

    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = Field(default=300, gt=0, le=900)
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimensions: int = Field(default=512, gt=0, le=16_000)
    similarity_threshold: float = Field(default=0.10, ge=0.0, le=1.0)
    similarity_ngram_min: int = Field(default=2, ge=1, le=8)
    similarity_ngram_max: int = Field(default=4, ge=1, le=8)
    similarity_min_sentence_chars: int = Field(default=12, ge=1, le=500)

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("API_PREFIX 必须以 / 开头")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.chunk_overlap_chars >= self.chunk_target_chars:
            raise ValueError("CHUNK_OVERLAP_CHARS 必须小于 CHUNK_TARGET_CHARS")
        if self.similarity_ngram_min > self.similarity_ngram_max:
            raise ValueError("SIMILARITY_NGRAM_MIN 不能大于 SIMILARITY_NGRAM_MAX")
        if (
            self.app_env == "production"
            and self.jwt_secret.get_secret_value()
            == "change-this-development-secret-before-production"
        ):
            raise ValueError("生产环境必须配置独立 JWT_SECRET")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
