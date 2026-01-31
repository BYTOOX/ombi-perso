from .auth import router as auth_router
from .search import router as search_router
from .requests import router as requests_router
from .admin import router as admin_router
from .plex import router as plex_router
from .transfers import router as transfers_router
from .services import router as services_router
from .monitoring import router as monitoring_router
from .analysis import router as analysis_router
from .ai import router as ai_router

__all__ = [
    "auth_router", "search_router", "requests_router", "admin_router",
    "plex_router", "transfers_router", "services_router", "monitoring_router",
    "analysis_router", "ai_router"
]


