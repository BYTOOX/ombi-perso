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
from .models.database import init_db
from .api.v1 import auth_router, search_router, requests_router, admin_router, plex_router, transfers_router, services_router, monitoring_router, analysis_router, ai_router, workflow_router
from .logging_config import setup_logging

# Configure logging with file handlers and module separation
setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()

# Background tasks
_sync_task = None


async def plex_sync_background_task():
    """Background task to sync Plex library every hour."""
    from .services.plex_cache_service import get_plex_cache_service
    
    logger.info("Starting Plex library background sync task")
    
    # Initial sync on startup (after a short delay to let services initialize)
    await asyncio.sleep(10)
    
    try:
        plex_cache = get_plex_cache_service()
        logger.info("Running initial Plex library sync...")
        result = plex_cache.sync_library(full_sync=True)
        logger.info(f"Initial sync complete: {result.message}")
    except Exception as e:
        logger.error(f"Initial Plex sync failed: {e}")
    
    # Then sync every hour
    while True:
        try:
            await asyncio.sleep(3600)  # 1 hour
            
            plex_cache = get_plex_cache_service()
            logger.info("Running scheduled Plex library sync...")
            result = plex_cache.sync_library(full_sync=False)  # Incremental sync
            logger.info(f"Scheduled sync complete: {result.message}")
            
        except asyncio.CancelledError:
            logger.info("Plex sync background task cancelled")
            break
        except Exception as e:
            logger.error(f"Scheduled Plex sync failed: {e}")
            # Continue after error, try again next hour


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    global _sync_task
    
    # Startup
    logger.info(f"Starting {settings.app_name}...")
    init_db()
    logger.info("Database initialized")

    # Initialize service configurations (migrate from .env if needed)
    from .services.service_config_service import init_service_configurations
    init_service_configurations()

    # Start background Plex sync task
    _sync_task = asyncio.create_task(plex_sync_background_task())
    logger.info("Plex sync background task started")

    # Start scheduler for background tasks
    from .services.scheduler_service import get_scheduler_service
    scheduler = get_scheduler_service()
    await scheduler.start()
    logger.info("Scheduler started")

    yield
    
    # Shutdown
    logger.info("Shutting down...")

    # Stop scheduler
    scheduler = get_scheduler_service()
    await scheduler.stop()
    logger.info("Scheduler stopped")

    # Cancel background sync task
    if _sync_task and not _sync_task.done():
        _sync_task.cancel()
        try:
            await _sync_task
        except asyncio.CancelledError:
            pass
        logger.info("Plex sync task stopped")

    # Close service connections
    from .services.media_search import get_media_search_service
    from .services.notifications import get_notification_service

    await get_media_search_service().close()
    await get_notification_service().close()


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Système de kiosque self-service pour demander des films, séries et animés",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routes
app.include_router(auth_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(requests_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(plex_router, prefix="/api/v1")
app.include_router(transfers_router, prefix="/api/v1")
app.include_router(services_router, prefix="/api/v1")
app.include_router(monitoring_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(workflow_router, prefix="/api/v1")


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
