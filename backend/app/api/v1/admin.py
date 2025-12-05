"""
Admin endpoints for user and system management.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import get_db, User, MediaRequest, Download
from ...models.user import UserRole
from ...models.request import RequestStatus
from ...models.download import DownloadStatus
from ...schemas.user import UserResponse, UserUpdate
from ...schemas.download import DownloadStats
from ...services.downloader import get_downloader_service
from ...services.plex_manager import get_plex_manager_service
from ...services.ai_agent import get_ai_agent_service
from ...config import get_settings
from .auth import get_current_admin

router = APIRouter(prefix="/admin", tags=["Admin"])
settings = get_settings()


# =========================================================================
# USER MANAGEMENT
# =========================================================================

@router.get("/users", response_model=List[UserResponse])
async def list_users(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Lister tous les utilisateurs."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Obtenir les détails d'un utilisateur."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    return UserResponse.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    update_data: UserUpdate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Mettre à jour un utilisateur."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    # Prevent self-demotion
    if user.id == current_user.id and update_data.role == UserRole.USER:
        raise HTTPException(
            status_code=400,
            detail="Vous ne pouvez pas vous rétrograder vous-même"
        )
    
    if update_data.email is not None:
        user.email = update_data.email
    if update_data.is_active is not None:
        user.is_active = update_data.is_active
    if update_data.role is not None:
        user.role = update_data.role
    
    await db.commit()
    await db.refresh(user)
    
    return UserResponse.model_validate(user)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Supprimer un utilisateur."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Vous ne pouvez pas vous supprimer vous-même"
        )
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    await db.delete(user)
    await db.commit()
    
    return {"message": "Utilisateur supprimé"}


# =========================================================================
# STATISTICS
# =========================================================================

@router.get("/stats")
async def get_stats(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Obtenir les statistiques globales."""
    # User count
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar()
    
    # Request counts by status
    request_stats = {}
    for status in RequestStatus:
        count = (await db.execute(
            select(func.count()).where(MediaRequest.status == status)
        )).scalar()
        request_stats[status.value] = count
    
    total_requests = sum(request_stats.values())
    
    # Download info
    downloader = get_downloader_service()
    disk_usage = downloader.get_disk_usage()
    
    return {
        "users": {
            "total": user_count
        },
        "requests": {
            "total": total_requests,
            "by_status": request_stats
        },
        "downloads": {
            "disk_usage_gb": disk_usage.get("total_size_gb", 0),
            "disk_limit_gb": disk_usage.get("limit_gb", settings.max_download_size_gb),
            "active_count": len(downloader.get_all_torrents())
        }
    }


@router.get("/downloads", response_model=DownloadStats)
async def get_download_stats(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Obtenir les statistiques de téléchargement."""
    # From database
    active = (await db.execute(
        select(func.count()).where(Download.status == DownloadStatus.DOWNLOADING)
    )).scalar()
    
    seeding = (await db.execute(
        select(func.count()).where(Download.status == DownloadStatus.SEEDING)
    )).scalar()
    
    queued = (await db.execute(
        select(func.count()).where(Download.status == DownloadStatus.QUEUED)
    )).scalar()
    
    # From qBittorrent
    downloader = get_downloader_service()
    disk_usage = downloader.get_disk_usage()
    
    return DownloadStats(
        active_downloads=active,
        seeding_count=seeding,
        queued_count=queued,
        completed_today=0,  # TODO: Calculate from downloads completed today
        total_download_speed=disk_usage.get("download_speed", 0),
        total_upload_speed=disk_usage.get("upload_speed", 0),
        disk_usage_gb=disk_usage.get("total_size_gb", 0),
        disk_limit_gb=settings.max_download_size_gb,
        disk_usage_percent=disk_usage.get("usage_percent", 0)
    )


# =========================================================================
# SYSTEM HEALTH
# =========================================================================

@router.get("/health")
async def health_check(
    current_user: User = Depends(get_current_admin)
):
    """Vérifier l'état de tous les services."""
    plex = get_plex_manager_service()
    downloader = get_downloader_service()
    ai = get_ai_agent_service()
    
    return {
        "plex": plex.health_check(),
        "qbittorrent": downloader.health_check(),
        "ollama": {
            "status": "ok" if await ai.health_check() else "error"
        },
        "database": {"status": "ok"}
    }


@router.get("/config")
async def get_config(
    current_user: User = Depends(get_current_admin)
):
    """Obtenir la configuration actuelle (sans secrets)."""
    from ...services.file_renamer import get_file_renamer_service
    
    renamer = get_file_renamer_service()
    library_paths = renamer.verify_library_paths()
    
    return {
        "app_name": settings.app_name,
        "max_requests_per_day": settings.max_requests_per_day,
        "seed_duration_hours": settings.seed_duration_hours,
        "max_download_size_gb": settings.max_download_size_gb,
        "library_paths": library_paths,
        "services": {
            "ollama_model": settings.ollama_model,
            "flaresolverr_configured": bool(settings.flaresolverr_url),
            "discord_configured": bool(settings.discord_webhook_url),
            "plex_configured": bool(settings.plex_url and settings.plex_token),
            "ygg_configured": bool(settings.ygg_username and settings.ygg_password)
        }
    }


# =========================================================================
# ACTIONS
# =========================================================================

@router.post("/scan-library")
async def trigger_library_scan(
    library_key: Optional[str] = None,
    current_user: User = Depends(get_current_admin)
):
    """Déclencher un scan de librairie Plex."""
    plex = get_plex_manager_service()
    success = plex.scan_library(library_key)
    
    if success:
        return {"message": "Scan démarré"}
    else:
        raise HTTPException(status_code=500, detail="Échec du scan Plex")


@router.post("/cleanup-seeds")
async def cleanup_seeds(
    current_user: User = Depends(get_current_admin)
):
    """Nettoyer les torrents qui ont fini de seeder."""
    downloader = get_downloader_service()
    count = downloader.cleanup_finished_seeds()
    
    return {"message": f"{count} torrent(s) supprimé(s)"}


@router.get("/libraries")
async def get_plex_libraries(
    current_user: User = Depends(get_current_admin)
):
    """Obtenir la liste des librairies Plex."""
    plex = get_plex_manager_service()
    return plex.get_libraries()
