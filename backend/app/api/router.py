from fastapi import APIRouter

from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.mvp5 import admin_router as mvp5_admin_router
from app.api.routes.mvp5 import public_router as announcements_router
from app.api.routes.mvp5 import user_router as mvp5_user_router
from app.api.routes.reports import reports_router, templates_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(knowledge_router, prefix="/knowledge-bases", tags=["knowledge"])
api_router.include_router(templates_router, prefix="/report-templates", tags=["reports"])
api_router.include_router(mvp5_user_router, prefix="/users/me", tags=["profile"])
api_router.include_router(announcements_router, prefix="/announcements", tags=["announcements"])
api_router.include_router(mvp5_admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(chat_router, prefix="/reports", tags=["chat"])
api_router.include_router(reports_router, prefix="/reports", tags=["reports"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
