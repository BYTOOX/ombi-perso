"""
API endpoints for release monitoring.
Allows admin to manage series monitoring and episode approvals.
"""
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ...models import User
from ...models.monitored_series import (
    MonitorType,
    QualityPreference,
    AudioPreference,
    MonitoringStatus
)
from ...models.episode_schedule import EpisodeStatus
from ...services.release_monitor_service import get_release_monitor_service
from .auth import get_current_admin

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


# =========================================================================
# SCHEMAS
# =========================================================================

class AddSeriesRequest(BaseModel):
    """Request schema for adding a series to monitoring."""
    tmdb_id: Optional[str] = Field(None, description="TMDB series ID")
    anilist_id: Optional[str] = Field(None, description="AniList anime ID")
    title: str = Field(..., description="Series title")
    original_title: Optional[str] = Field(None, description="Original title")
    year: Optional[int] = Field(None, description="First air year")
    media_type: str = Field("series", description="Type: series or anime")
    poster_url: Optional[str] = Field(None, description="Poster image URL")
    backdrop_url: Optional[str] = Field(None, description="Backdrop image URL")
    monitor_type: str = Field(MonitorType.NEW_EPISODES.value, description="Monitoring type")
    quality_preference: str = Field(QualityPreference.FHD_1080P.value, description="Quality preference")
    audio_preference: str = Field(AudioPreference.MULTI.value, description="Audio preference")


class UpdateSeriesRequest(BaseModel):
    """Request schema for updating series settings."""
    monitor_type: Optional[str] = None
    quality_preference: Optional[str] = None
    audio_preference: Optional[str] = None
    current_season: Optional[int] = None
    current_episode: Optional[int] = None


class SeriesResponse(BaseModel):
    """Response schema for a monitored series."""
    id: int
    tmdb_id: Optional[str]
    anilist_id: Optional[str]
    title: str
    original_title: Optional[str]
    year: Optional[int]
    media_type: str
    poster_url: Optional[str]
    monitor_type: str
    quality_preference: str
    audio_preference: str
    status: str
    total_seasons: Optional[int]
    current_season: int
    current_episode: int
    next_air_date: Optional[str]
    last_checked_at: Optional[str]
    created_at: Optional[str]


class EpisodeResponse(BaseModel):
    """Response schema for an episode."""
    id: int
    monitored_series_id: int
    season: int
    episode: int
    episode_code: str
    episode_title: Optional[str]
    air_date: Optional[str]
    is_aired: bool
    status: str
    status_message: Optional[str]
    found_torrent_name: Optional[str]
    found_torrent_size: Optional[str]
    found_torrent_seeders: Optional[int]
    found_torrent_quality: Optional[str]
    found_torrent_audio: Optional[str]
    search_attempts: int


class CalendarEntry(BaseModel):
    """Response schema for a calendar entry."""
    id: int
    series_id: int
    series_title: str
    series_poster: Optional[str]
    season: int
    episode: int
    episode_code: str
    episode_title: Optional[str]
    air_date: str
    is_aired: bool
    status: str
    found_torrent_name: Optional[str]


# =========================================================================
# SERIES ENDPOINTS
# =========================================================================

@router.get("/series", response_model=List[SeriesResponse])
async def list_monitored_series(
    status: Optional[str] = Query(None, description="Filter by status"),
    current_user: User = Depends(get_current_admin)
):
    """
    Lister toutes les séries suivies.
    Filtrable par statut (active, paused, ended).
    """
    monitor_service = get_release_monitor_service()
    series_list = await monitor_service.get_all_series(status=status)

    return [
        SeriesResponse(
            id=s.id,
            tmdb_id=s.tmdb_id,
            anilist_id=s.anilist_id,
            title=s.title,
            original_title=s.original_title,
            year=s.year,
            media_type=s.media_type,
            poster_url=s.poster_url,
            monitor_type=s.monitor_type,
            quality_preference=s.quality_preference,
            audio_preference=s.audio_preference,
            status=s.status,
            total_seasons=s.total_seasons,
            current_season=s.current_season,
            current_episode=s.current_episode,
            next_air_date=s.next_air_date.isoformat() if s.next_air_date else None,
            last_checked_at=s.last_checked_at.isoformat() if s.last_checked_at else None,
            created_at=s.created_at.isoformat() if s.created_at else None
        )
        for s in series_list
    ]


@router.post("/series", response_model=SeriesResponse)
async def add_series(
    request: AddSeriesRequest,
    current_user: User = Depends(get_current_admin)
):
    """
    Ajouter une série au monitoring.
    Récupère automatiquement le calendrier des épisodes depuis TMDB.
    """
    # Validate at least one ID provided
    if not request.tmdb_id and not request.anilist_id:
        raise HTTPException(
            status_code=400,
            detail="Au moins un identifiant (tmdb_id ou anilist_id) est requis"
        )

    # Validate enum values
    try:
        MonitorType(request.monitor_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Type de monitoring invalide: {request.monitor_type}"
        )

    try:
        QualityPreference(request.quality_preference)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Préférence qualité invalide: {request.quality_preference}"
        )

    try:
        AudioPreference(request.audio_preference)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Préférence audio invalide: {request.audio_preference}"
        )

    monitor_service = get_release_monitor_service()

    series = await monitor_service.add_series(
        tmdb_id=request.tmdb_id,
        anilist_id=request.anilist_id,
        title=request.title,
        original_title=request.original_title,
        year=request.year,
        media_type=request.media_type,
        poster_url=request.poster_url,
        backdrop_url=request.backdrop_url,
        monitor_type=request.monitor_type,
        quality_preference=request.quality_preference,
        audio_preference=request.audio_preference,
        user_id=current_user.id
    )

    return SeriesResponse(
        id=series.id,
        tmdb_id=series.tmdb_id,
        anilist_id=series.anilist_id,
        title=series.title,
        original_title=series.original_title,
        year=series.year,
        media_type=series.media_type,
        poster_url=series.poster_url,
        monitor_type=series.monitor_type,
        quality_preference=series.quality_preference,
        audio_preference=series.audio_preference,
        status=series.status,
        total_seasons=series.total_seasons,
        current_season=series.current_season,
        current_episode=series.current_episode,
        next_air_date=series.next_air_date.isoformat() if series.next_air_date else None,
        last_checked_at=series.last_checked_at.isoformat() if series.last_checked_at else None,
        created_at=series.created_at.isoformat() if series.created_at else None
    )


@router.get("/series/{series_id}", response_model=SeriesResponse)
async def get_series(
    series_id: int,
    current_user: User = Depends(get_current_admin)
):
    """Obtenir les détails d'une série suivie."""
    monitor_service = get_release_monitor_service()
    series = await monitor_service.get_series(series_id)

    if not series:
        raise HTTPException(status_code=404, detail="Série non trouvée")

    return SeriesResponse(
        id=series.id,
        tmdb_id=series.tmdb_id,
        anilist_id=series.anilist_id,
        title=series.title,
        original_title=series.original_title,
        year=series.year,
        media_type=series.media_type,
        poster_url=series.poster_url,
        monitor_type=series.monitor_type,
        quality_preference=series.quality_preference,
        audio_preference=series.audio_preference,
        status=series.status,
        total_seasons=series.total_seasons,
        current_season=series.current_season,
        current_episode=series.current_episode,
        next_air_date=series.next_air_date.isoformat() if series.next_air_date else None,
        last_checked_at=series.last_checked_at.isoformat() if series.last_checked_at else None,
        created_at=series.created_at.isoformat() if series.created_at else None
    )


@router.put("/series/{series_id}", response_model=SeriesResponse)
async def update_series(
    series_id: int,
    request: UpdateSeriesRequest,
    current_user: User = Depends(get_current_admin)
):
    """Mettre à jour les paramètres de monitoring d'une série."""
    monitor_service = get_release_monitor_service()

    # Validate enum values if provided
    if request.monitor_type:
        try:
            MonitorType(request.monitor_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Type de monitoring invalide: {request.monitor_type}"
            )

    if request.quality_preference:
        try:
            QualityPreference(request.quality_preference)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Préférence qualité invalide: {request.quality_preference}"
            )

    if request.audio_preference:
        try:
            AudioPreference(request.audio_preference)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Préférence audio invalide: {request.audio_preference}"
            )

    series = await monitor_service.update_series(
        series_id,
        **request.model_dump(exclude_none=True)
    )

    if not series:
        raise HTTPException(status_code=404, detail="Série non trouvée")

    return SeriesResponse(
        id=series.id,
        tmdb_id=series.tmdb_id,
        anilist_id=series.anilist_id,
        title=series.title,
        original_title=series.original_title,
        year=series.year,
        media_type=series.media_type,
        poster_url=series.poster_url,
        monitor_type=series.monitor_type,
        quality_preference=series.quality_preference,
        audio_preference=series.audio_preference,
        status=series.status,
        total_seasons=series.total_seasons,
        current_season=series.current_season,
        current_episode=series.current_episode,
        next_air_date=series.next_air_date.isoformat() if series.next_air_date else None,
        last_checked_at=series.last_checked_at.isoformat() if series.last_checked_at else None,
        created_at=series.created_at.isoformat() if series.created_at else None
    )


@router.delete("/series/{series_id}")
async def delete_series(
    series_id: int,
    current_user: User = Depends(get_current_admin)
):
    """Retirer une série du monitoring."""
    monitor_service = get_release_monitor_service()
    deleted = await monitor_service.remove_series(series_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Série non trouvée")

    return {"success": True, "message": "Série retirée du monitoring"}


@router.post("/series/{series_id}/pause")
async def pause_series(
    series_id: int,
    current_user: User = Depends(get_current_admin)
):
    """Mettre en pause le monitoring d'une série."""
    monitor_service = get_release_monitor_service()
    success = await monitor_service.pause_series(series_id)

    if not success:
        raise HTTPException(status_code=404, detail="Série non trouvée")

    return {"success": True, "message": "Monitoring mis en pause"}


@router.post("/series/{series_id}/resume")
async def resume_series(
    series_id: int,
    current_user: User = Depends(get_current_admin)
):
    """Reprendre le monitoring d'une série."""
    monitor_service = get_release_monitor_service()
    success = await monitor_service.resume_series(series_id)

    if not success:
        raise HTTPException(status_code=404, detail="Série non trouvée")

    return {"success": True, "message": "Monitoring repris"}


@router.post("/series/{series_id}/refresh")
async def refresh_series_schedule(
    series_id: int,
    current_user: User = Depends(get_current_admin)
):
    """Rafraîchir le calendrier des épisodes depuis TMDB."""
    monitor_service = get_release_monitor_service()
    count = await monitor_service.refresh_episode_schedule(series_id)

    return {
        "success": True,
        "message": f"Calendrier mis à jour ({count} épisodes ajoutés)"
    }


# =========================================================================
# CALENDAR ENDPOINTS
# =========================================================================

@router.get("/calendar", response_model=List[CalendarEntry])
async def get_calendar(
    days_back: int = Query(7, ge=0, le=30, description="Jours passés à inclure"),
    days_ahead: int = Query(14, ge=1, le=90, description="Jours à venir à inclure"),
    current_user: User = Depends(get_current_admin)
):
    """
    Obtenir le calendrier des épisodes à venir et récents.
    Par défaut: 7 jours passés et 14 jours à venir.
    """
    monitor_service = get_release_monitor_service()

    start_date = datetime.utcnow() - timedelta(days=days_back)
    end_date = datetime.utcnow() + timedelta(days=days_ahead)

    calendar = await monitor_service.get_calendar(
        start_date=start_date,
        end_date=end_date
    )

    return [CalendarEntry(**entry) for entry in calendar]


# =========================================================================
# EPISODE ENDPOINTS
# =========================================================================

@router.get("/episodes/pending", response_model=List[EpisodeResponse])
async def get_pending_episodes(
    current_user: User = Depends(get_current_admin)
):
    """Lister les épisodes en attente d'approbation."""
    monitor_service = get_release_monitor_service()
    episodes = await monitor_service.get_pending_episodes()

    return [
        EpisodeResponse(
            id=ep.id,
            monitored_series_id=ep.monitored_series_id,
            season=ep.season,
            episode=ep.episode,
            episode_code=ep.episode_code,
            episode_title=ep.episode_title,
            air_date=ep.air_date.isoformat() if ep.air_date else None,
            is_aired=ep.is_aired,
            status=ep.status,
            status_message=ep.status_message,
            found_torrent_name=ep.found_torrent_name,
            found_torrent_size=ep.found_torrent_size,
            found_torrent_seeders=ep.found_torrent_seeders,
            found_torrent_quality=ep.found_torrent_quality,
            found_torrent_audio=ep.found_torrent_audio,
            search_attempts=ep.search_attempts
        )
        for ep in episodes
    ]


@router.post("/episodes/{episode_id}/approve")
async def approve_episode(
    episode_id: int,
    current_user: User = Depends(get_current_admin)
):
    """Approuver un épisode pour téléchargement."""
    monitor_service = get_release_monitor_service()
    success = await monitor_service.approve_episode(episode_id, current_user.id)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Impossible d'approuver l'épisode (non trouvé ou pas en attente)"
        )

    return {"success": True, "message": "Épisode approuvé, téléchargement en cours"}


@router.post("/episodes/{episode_id}/skip")
async def skip_episode(
    episode_id: int,
    current_user: User = Depends(get_current_admin)
):
    """Ignorer un épisode (ne sera pas téléchargé)."""
    monitor_service = get_release_monitor_service()
    success = await monitor_service.skip_episode(episode_id)

    if not success:
        raise HTTPException(status_code=404, detail="Épisode non trouvé")

    return {"success": True, "message": "Épisode ignoré"}


@router.post("/episodes/{episode_id}/retry")
async def retry_episode_search(
    episode_id: int,
    current_user: User = Depends(get_current_admin)
):
    """Relancer la recherche pour un épisode."""
    monitor_service = get_release_monitor_service()
    success = await monitor_service.retry_episode_search(episode_id)

    if not success:
        raise HTTPException(status_code=404, detail="Épisode non trouvé")

    return {"success": True, "message": "Recherche relancée"}


# =========================================================================
# TASK ENDPOINTS
# =========================================================================

@router.post("/tasks/check-episodes")
async def trigger_episode_check(
    current_user: User = Depends(get_current_admin)
):
    """Déclencher manuellement une vérification des épisodes."""
    monitor_service = get_release_monitor_service()
    results = await monitor_service.check_for_new_episodes()

    return {
        "success": True,
        "message": "Vérification terminée",
        "results": results
    }


@router.post("/tasks/update-aired")
async def trigger_aired_update(
    current_user: User = Depends(get_current_admin)
):
    """Mettre à jour le statut des épisodes diffusés."""
    monitor_service = get_release_monitor_service()
    count = await monitor_service.update_aired_episodes()

    return {
        "success": True,
        "message": f"{count} épisode(s) mis à jour"
    }


# =========================================================================
# STATISTICS
# =========================================================================

@router.get("/stats")
async def get_monitoring_stats(
    current_user: User = Depends(get_current_admin)
):
    """Obtenir les statistiques de monitoring."""
    monitor_service = get_release_monitor_service()

    all_series = await monitor_service.get_all_series()
    pending_episodes = await monitor_service.get_pending_episodes()

    # Count by status
    active_count = sum(1 for s in all_series if s.status == MonitoringStatus.ACTIVE.value)
    paused_count = sum(1 for s in all_series if s.status == MonitoringStatus.PAUSED.value)
    ended_count = sum(1 for s in all_series if s.status == MonitoringStatus.ENDED.value)

    # Count by type
    series_count = sum(1 for s in all_series if s.media_type == "series")
    anime_count = sum(1 for s in all_series if s.media_type == "anime")

    return {
        "total_series": len(all_series),
        "by_status": {
            "active": active_count,
            "paused": paused_count,
            "ended": ended_count
        },
        "by_type": {
            "series": series_count,
            "anime": anime_count
        },
        "pending_approvals": len(pending_episodes)
    }
