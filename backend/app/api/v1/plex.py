"""
Plex integration endpoints.
Handles library sync, availability checks, and Plex webhooks.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel

from ...dependencies import (
    get_plex_cache_service,
    get_plex_manager_service,
    get_notification_service
)
from ...services.plex_cache_service import PlexCacheService
from ...services.notifications import NotificationService
from ...models.user import User
from .auth import get_current_user, get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plex", tags=["Plex"])


# =============================================================================
# Response Models
# =============================================================================

class SyncResponse(BaseModel):
    success: bool
    items_synced: int
    items_skipped: int
    items_without_guid: int
    duration_seconds: float
    message: str


class AvailabilityResponse(BaseModel):
    available: bool
    plex_rating_key: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    quality_info: Optional[dict] = None
    audio_languages: list = []
    subtitle_languages: list = []
    file_size_gb: Optional[float] = None
    seasons_available: list = []
    total_episodes: Optional[int] = None


class SeasonsAvailabilityResponse(BaseModel):
    available: bool
    seasons: list = []
    total_episodes: int = 0
    quality_info: Optional[dict] = None
    audio_languages: list = []


class SyncStatusResponse(BaseModel):
    last_sync_at: Optional[str] = None
    last_sync_count: int = 0
    total_items: int = 0
    items_without_guid: int = 0
    last_sync_message: Optional[str] = None
    sync_in_progress: bool = False


class EpisodeInfo(BaseModel):
    episode_number: int
    title: str
    summary: Optional[str] = None
    duration_ms: Optional[int] = None
    resolution: Optional[str] = None
    video_codec: Optional[str] = None
    audio_languages: list = []
    subtitle_languages: list = []


class SeasonInfo(BaseModel):
    season_number: int
    title: Optional[str] = None
    episode_count: int
    episodes: list[EpisodeInfo] = []


class SeriesEpisodesResponse(BaseModel):
    show_title: str
    total_seasons: int
    seasons: list[SeasonInfo] = []


# =============================================================================
# Library Sync Endpoints
# =============================================================================

@router.post("/sync", response_model=SyncResponse)
async def sync_plex_library(
    full: bool = False,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_admin),
    plex_cache: PlexCacheService = Depends(get_plex_cache_service)
):
    """
    Trigger Plex library synchronization.
    
    - **full=False**: Incremental sync (only new items since last sync)
    - **full=True**: Full resync (clears cache and rescans everything)
    
    Requires admin privileges.
    """
    logger.info(f"Library sync requested by {current_user.username} (full={full})")
    
    result = plex_cache.sync_library(full_sync=full)
    
    return SyncResponse(
        success=result.success,
        items_synced=result.items_synced,
        items_skipped=result.items_skipped,
        items_without_guid=result.items_without_guid,
        duration_seconds=result.duration_seconds,
        message=result.message
    )


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status(
    current_user: User = Depends(get_current_user),
    plex_cache: PlexCacheService = Depends(get_plex_cache_service)
):
    """
    Get current sync status.
    Shows when last sync occurred and how many items are cached.
    """
    status = plex_cache.get_sync_status()
    return SyncStatusResponse(**status)


# =============================================================================
# Availability Endpoints
# =============================================================================

@router.get("/availability/{media_type}/{tmdb_id}", response_model=AvailabilityResponse)
async def get_availability(
    media_type: str,
    tmdb_id: str,
    current_user: User = Depends(get_current_user),
    plex_cache: PlexCacheService = Depends(get_plex_cache_service)
):
    """
    Get detailed availability info for a specific media item.
    
    Used by frontend modal to show:
    - Quality (resolution, codec)
    - Audio languages
    - Subtitle languages
    - File size
    - For series: available seasons
    """
    availability = plex_cache.get_detailed_availability(tmdb_id, media_type)
    
    if not availability:
        return AvailabilityResponse(available=False)
    
    return AvailabilityResponse(**availability)


@router.get("/availability/seasons/{tmdb_id}", response_model=SeasonsAvailabilityResponse)
async def get_seasons_availability(
    tmdb_id: str,
    current_user: User = Depends(get_current_user),
    plex_cache: PlexCacheService = Depends(get_plex_cache_service)
):
    """
    Get which seasons are available for a TV series.
    
    Used by frontend to show season selector with available/unavailable status.
    """
    result = plex_cache.check_seasons_availability(tmdb_id)
    return SeasonsAvailabilityResponse(**result)


@router.get("/series/{rating_key}/episodes", response_model=SeriesEpisodesResponse)
async def get_series_episodes(
    rating_key: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed episode information for a TV series.
    
    Returns all seasons with their episodes including:
    - Episode number and title
    - Resolution (4K, 1080p, 720p, etc.)
    - Video codec (HEVC, H264, etc.)
    - Audio languages
    - Subtitle languages
    
    Used by frontend to display available episodes in the media modal.
    """
    plex_manager = get_plex_manager_service()
    result = plex_manager.get_series_episodes(rating_key)
    
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Series not found or Plex not connected"
        )
    
    return SeriesEpisodesResponse(**result)


# =============================================================================
# Plex Webhooks (Plex Pass feature)
# =============================================================================

@router.post("/webhook")
async def plex_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    plex_cache: PlexCacheService = Depends(get_plex_cache_service),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """
    Receive Plex webhooks for real-time cache updates.
    
    Supported events:
    - library.new: New item added to library
    - library.on.deck: Item added to On Deck (not used)
    - media.play: Playback started (not used)
    
    Configure in Plex: Settings > Webhooks > Add Webhook
    URL: https://your-domain/api/v1/plex/webhook
    """
    try:
        # Plex sends webhook as multipart form data
        form = await request.form()
        payload_str = form.get('payload', '{}')
        
        import json
        payload = json.loads(payload_str)
        
        event = payload.get('event', '')
        logger.info(f"Received Plex webhook: {event}")
        
        if event == 'library.new':
            # New item added - trigger incremental sync in background
            logger.info("New library item detected, triggering background sync")
            background_tasks.add_task(plex_cache.sync_library, False)
            
            # Get item info for logging
            metadata = payload.get('Metadata', {})
            title = metadata.get('title', 'Unknown')
            item_type = metadata.get('type', 'unknown')
            logger.info(f"New {item_type} added: {title}")
            
            return {"status": "ok", "message": f"Sync triggered for new {item_type}: {title}"}
        
        elif event == 'library.on.deck':
            # Item added to On Deck - not used for cache
            return {"status": "ok", "message": "Event ignored (on.deck)"}
        
        elif event == 'media.play':
            # Playback started - not used for cache
            return {"status": "ok", "message": "Event ignored (play)"}
        
        else:
            logger.debug(f"Unhandled Plex webhook event: {event}")
            return {"status": "ok", "message": f"Event ignored ({event})"}
    
    except Exception as e:
        logger.error(f"Error processing Plex webhook: {e}")
        return {"status": "error", "message": str(e)}


# =============================================================================
# Admin Endpoints
# =============================================================================

@router.get("/libraries")
async def get_plex_libraries(
    current_user: User = Depends(get_current_admin)
):
    """
    Get list of Plex libraries.
    Admin only - used in admin panel for library management.
    """
    plex = get_plex_manager_service()
    libraries = plex.get_libraries()
    return {"libraries": libraries}


@router.get("/cache/stats")
async def get_cache_stats(
    current_user: User = Depends(get_current_admin),
    plex_cache: PlexCacheService = Depends(get_plex_cache_service)
):
    """
    Get cache statistics for admin panel.
    Shows breakdown by library, items without GUIDs, etc.
    """
    from ...models.database import SessionLocal
    from ...models.plex_library import PlexLibraryItem
    from sqlalchemy import func
    
    with SessionLocal() as db:
        # Count by library
        by_library = db.query(
            PlexLibraryItem.plex_library_title,
            func.count(PlexLibraryItem.id)
        ).group_by(PlexLibraryItem.plex_library_title).all()
        
        # Count without GUIDs
        without_guid = db.query(PlexLibraryItem).filter(
            PlexLibraryItem.tmdb_id.is_(None),
            PlexLibraryItem.tvdb_id.is_(None),
            PlexLibraryItem.imdb_id.is_(None)
        ).count()
        
        # Total count
        total = db.query(PlexLibraryItem).count()
        
        return {
            "total_items": total,
            "items_without_guid": without_guid,
            "by_library": {lib: count for lib, count in by_library}
        }


@router.get("/servers")
async def list_plex_servers(
    current_user: User = Depends(get_current_admin)
):
    """
    List Plex servers accessible with the admin token.

    Used in admin panel to configure the authorized server (machine_identifier)
    for restricting SSO login.

    Returns list of servers with:
    - name: Server display name
    - machineIdentifier: Unique server ID (used for access control)
    - owned: Whether the admin owns this server
    """
    from ...services.plex_access_service import get_user_plex_servers
    from ...services.service_config_service import get_service_config_service
    from ...config import get_settings

    settings = get_settings()
    config_service = get_service_config_service()

    # Try to get token from DB first, then fallback to .env
    plex_config = await config_service.get_decrypted_config("plex")
    admin_token = plex_config.get("token") if plex_config else None

    if not admin_token:
        admin_token = settings.plex_token

    if not admin_token:
        raise HTTPException(
            status_code=400,
            detail="Token Plex non configuré"
        )

    try:
        servers = await get_user_plex_servers(admin_token)
        return {"servers": servers}
    except Exception as e:
        logger.error(f"Error listing Plex servers: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la récupération des serveurs: {str(e)}"
        )
