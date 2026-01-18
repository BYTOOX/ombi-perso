"""
Dependency Injection for FastAPI endpoints.

This module provides all service dependencies using FastAPI's Depends() pattern,
replacing the old singleton pattern with proper lifecycle management.

Service Hierarchy:
    Level 0: Base services (settings, database)
    Level 1: HTTP clients (media_search, ai_agent, notifications, plex_manager)
    Level 2: Business logic (title_resolver, file_renamer, torrent_scraper, downloader)
    Level 3: Orchestration (pipeline, plex_cache)

All services are created per-request with proper cleanup in finally blocks.
"""
from typing import AsyncGenerator, Generator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .models.database import AsyncSessionLocal, SessionLocal
from .config import Settings, get_settings


# =============================================================================
# DATABASE DEPENDENCIES
# =============================================================================

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async database session dependency.

    Automatically commits on success, rolls back on exception.
    Use this for all async endpoints.

    Usage:
        @router.get("/")
        async def endpoint(db: AsyncSession = Depends(get_async_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_db() -> Generator[Session, None, None]:
    """
    Sync database session dependency.

    Use only for legacy sync code. Prefer get_async_db() for new code.

    Usage:
        @router.get("/")
        def sync_endpoint(db: Session = Depends(get_sync_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# CONFIGURATION DEPENDENCIES
# =============================================================================

@lru_cache
def get_settings_cached() -> Settings:
    """
    Cached settings (singleton per application lifecycle).

    Settings are immutable and loaded once at startup.
    """
    return get_settings()


def get_settings_dependency() -> Settings:
    """
    Settings dependency for injection.

    Usage:
        @router.get("/")
        async def endpoint(settings: Settings = Depends(get_settings_dependency)):
            ...
    """
    return get_settings_cached()


# =============================================================================
# LEVEL 0: BASE SERVICES
# =============================================================================

def get_settings_service(
    db: AsyncSession = Depends(get_async_db)
):
    """
    Settings service dependency.

    Manages system settings stored in database (library paths, rename templates, etc.).
    """
    from .services.settings_service import SettingsService
    return SettingsService(db)


# =============================================================================
# LEVEL 1: HTTP CLIENT SERVICES
# =============================================================================

async def get_media_search_service(
    settings: Settings = Depends(get_settings_dependency)
) -> AsyncGenerator:
    """
    Media search service dependency (TMDB + AniList).

    Automatically closes httpx client on cleanup.
    """
    from .services.media_search import MediaSearchService

    service = MediaSearchService(settings)
    try:
        yield service
    finally:
        # Cleanup httpx client if needed
        if hasattr(service, '_client') and service._client:
            await service._client.aclose()


async def get_ai_agent_service(
    settings: Settings = Depends(get_settings_dependency)
) -> AsyncGenerator:
    """
    AI agent service dependency (Ollama/Qwen).

    Automatically closes httpx client on cleanup.
    """
    from .services.ai_agent import AIAgentService

    service = AIAgentService(settings)
    try:
        yield service
    finally:
        # Cleanup httpx client
        if hasattr(service, '_client') and service._client:
            await service._client.aclose()


async def get_notification_service(
    settings: Settings = Depends(get_settings_dependency)
) -> AsyncGenerator:
    """
    Notification service dependency (Discord webhooks).

    Automatically closes httpx client on cleanup.
    """
    from .services.notifications import NotificationService

    service = NotificationService(settings)
    try:
        yield service
    finally:
        # Cleanup httpx client
        if hasattr(service, '_client') and service._client:
            await service._client.aclose()


def get_plex_manager_service(
    settings: Settings = Depends(get_settings_dependency),
    settings_service = Depends(get_settings_service)
):
    """
    Plex manager service dependency.

    Note: Kept sync because PlexAPI library is sync-only.
    """
    from .services.plex_manager import PlexManagerService

    return PlexManagerService(settings, settings_service)


# =============================================================================
# LEVEL 2: BUSINESS LOGIC SERVICES
# =============================================================================

def get_title_resolver_service(
    settings: Settings = Depends(get_settings_dependency),
    settings_service = Depends(get_settings_service)
):
    """
    Title resolver service dependency (TMDB/TVDB title resolution).

    Used for accurate naming and metadata lookup.
    """
    from .services.title_resolver import TitleResolverService

    return TitleResolverService(settings, settings_service)


async def get_file_renamer_service(
    settings_service = Depends(get_settings_service),
    title_resolver = Depends(get_title_resolver_service)
):
    """
    File renamer service dependency (Plex-compatible naming).

    IMPORTANT: Now fully async (fixed blocking async call issue).
    """
    from .services.file_renamer import FileRenamerService

    return FileRenamerService(settings_service, title_resolver)


async def get_torrent_scraper_service(
    settings: Settings = Depends(get_settings_dependency),
    media_search = Depends(get_media_search_service)
):
    """
    Torrent scraper service dependency (YGG + FlareSolverr).

    Searches and downloads torrents from YGGtorrent.
    """
    from .services.torrent_scraper import TorrentScraperService

    return TorrentScraperService(settings, media_search)


async def get_downloader_service(
    settings: Settings = Depends(get_settings_dependency)
) -> AsyncGenerator:
    """
    Downloader service dependency (qBittorrent API).

    Manages torrent downloads and seeding.
    """
    from .services.downloader import DownloaderService

    service = DownloaderService(settings)
    try:
        yield service
    finally:
        # Cleanup if service has async cleanup
        if hasattr(service, 'close'):
            await service.close()


# =============================================================================
# LEVEL 3: ORCHESTRATION SERVICES
# =============================================================================

async def get_plex_cache_service(
    db: AsyncSession = Depends(get_async_db),
    plex_manager = Depends(get_plex_manager_service)
):
    """
    Plex cache service dependency.

    Caches Plex library metadata for fast lookups.
    """
    from .services.plex_cache_service import PlexCacheService

    return PlexCacheService(db, plex_manager)


async def get_pipeline_service(
    db: AsyncSession = Depends(get_async_db),
    scraper = Depends(get_torrent_scraper_service),
    ai = Depends(get_ai_agent_service),
    downloader = Depends(get_downloader_service),
    renamer = Depends(get_file_renamer_service),
    plex = Depends(get_plex_manager_service),
    notifier = Depends(get_notification_service)
):
    """
    Request pipeline service dependency.

    Orchestrates the full request workflow:
        1. Search torrents (scraper)
        2. AI selection (ai)
        3. Download (downloader)
        4. Rename (renamer)
        5. Plex scan (plex)
        6. Notify (notifier)

    All services are automatically injected and cleaned up.
    """
    from .services.pipeline import RequestPipelineService

    return RequestPipelineService(
        db=db,
        scraper=scraper,
        ai=ai,
        downloader=downloader,
        renamer=renamer,
        plex=plex,
        notifier=notifier
    )


# =============================================================================
# FUTURE: PHASE 1-3 DEPENDENCIES (Placeholder)
# =============================================================================

# Phase 1: Series Follow
# async def get_follow_manager_service(...):
#     from .services.automation.follow_manager import FollowManagerService
#     return FollowManagerService(...)

# Phase 2: Upgrade Monitor
# async def get_upgrade_monitor_service(...):
#     from .services.quality.upgrade_monitor import UpgradeMonitorService
#     return UpgradeMonitorService(...)

# Phase 3: AI Library Analyzer
# async def get_library_analyzer_service(...):
#     from .services.ai.library_analyzer import LibraryAnalyzerService
#     return LibraryAnalyzerService(...)
