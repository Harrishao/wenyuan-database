from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    name: str
    environment: str
    status: Literal["ok", "degraded"]
    version: str
    services: dict[str, str]
