from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
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
    cors_origins: str = "http://localhost:5173"
    storage_root: Path = Path("./data/uploads")

    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimensions: int = Field(default=512, gt=0, le=16_000)

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("API_PREFIX 必须以 / 开头")
        return value.rstrip("/")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
