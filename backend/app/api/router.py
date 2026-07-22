from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.reports import reports_router, templates_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(knowledge_router, prefix="/knowledge-bases", tags=["knowledge"])
api_router.include_router(templates_router, prefix="/report-templates", tags=["reports"])
api_router.include_router(reports_router, prefix="/reports", tags=["reports"])
