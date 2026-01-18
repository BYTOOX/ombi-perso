"""
Plex Kiosk - FastAPI Application Entry Point
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from .config import get_settings
from .api.v1 import auth_router, search_router, requests_router, admin_router, plex_router, transfers_router
from .logging_config import setup_logging

# Configure logging with file handlers and module separation
setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info(f"Starting {settings.app_name}...")
    logger.info("Database migrations handled by Alembic")
    logger.info("Plex sync handled by Celery Beat")

    yield

    # Shutdown
    logger.info("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Système de kiosque self-service pour demander des films, séries et animés",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None
)

# =============================================================================
# CORS Configuration (Security)
# =============================================================================

# Build allowed origins list based on environment
allowed_origins = []

if settings.debug:
    # Development: Allow localhost on various ports
    allowed_origins = [
        "http://localhost:8765",      # Backend dev
        "http://localhost:5173",      # Vite dev server
        "http://localhost:3000",      # Alternative dev port
        "http://127.0.0.1:8765",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    logger.info("CORS: Development mode - allowing localhost origins")
else:
    # Production: Only configured domains
    if settings.frontend_url:
        allowed_origins.append(settings.frontend_url)

    if settings.cors_origins:
        # Parse comma-separated origins
        additional_origins = [
            origin.strip()
            for origin in settings.cors_origins.split(",")
            if origin.strip()
        ]
        allowed_origins.extend(additional_origins)

    if not allowed_origins:
        logger.warning(
            "CORS: Production mode but no origins configured! "
            "Set FRONTEND_URL or CORS_ORIGINS in environment."
        )

logger.info(f"CORS allowed origins: {allowed_origins}")

# Add CORS middleware with secure configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Accept",
        "Accept-Language",
        "Content-Language",
    ],
    expose_headers=["Content-Range", "X-Content-Range"],
    max_age=3600,  # Cache preflight requests for 1 hour
)

# API Routes
app.include_router(auth_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(requests_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(plex_router, prefix="/api/v1")
app.include_router(transfers_router, prefix="/api/v1")


# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "app": settings.app_name}


# Static files & SPA fallback
# In Docker: /app/app/main.py -> /app/frontend/
# Locally: backend/app/main.py -> frontend/
frontend_path = Path(__file__).parent.parent / "frontend"

if frontend_path.exists():
    # Serve static files
    app.mount("/static", StaticFiles(directory=str(frontend_path / "static")), name="static")
    
    @app.get("/")
    async def serve_index():
        """Serve index.html for root path."""
        return FileResponse(frontend_path / "index.html")
    
    @app.get("/admin")
    async def serve_admin():
        """Serve admin.html for /admin path."""
        return FileResponse(frontend_path / "admin.html")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the SPA for all non-API routes."""
        # Check if file exists
        file_path = frontend_path / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        
        # Check if .html version exists (for clean URLs)
        html_path = frontend_path / f"{full_path}.html"
        if html_path.is_file():
            return FileResponse(html_path)
        
        # Otherwise serve index.html (SPA routing)
        index_path = frontend_path / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        
        return {"error": "Frontend not found"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=settings.debug
    )
