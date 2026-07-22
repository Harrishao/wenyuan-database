from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.schemas.health import HealthResponse

router = APIRouter()
settings = get_settings()


def health_payload(*, health_status: str, services: dict[str, str]) -> HealthResponse:
    return HealthResponse(
        name=settings.app_name,
        environment=settings.app_env,
        status=health_status,
        version=settings.app_version,
        services=services,
    )


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return health_payload(health_status="ok", services={"api": "up"})


@router.get("/ready", response_model=HealthResponse)
async def readiness(response: Response) -> HealthResponse:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return health_payload(health_status="degraded", services={"api": "up", "database": "down"})
    return health_payload(health_status="ok", services={"api": "up", "database": "up"})
