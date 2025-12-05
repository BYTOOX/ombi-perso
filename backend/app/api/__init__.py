from .auth import router as auth_router
from .search import router as search_router
from .requests import router as requests_router
from .admin import router as admin_router

__all__ = ["auth_router", "search_router", "requests_router", "admin_router"]
