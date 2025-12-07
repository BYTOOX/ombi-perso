"""
Admin endpoints for user and system management.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from argon2 import PasswordHasher

from ...models import get_db, User, MediaRequest, Download
from ...models.user import UserRole, UserStatus
from ...models.request import RequestStatus
from ...models.download import DownloadStatus
from ...schemas.user import UserResponse, UserUpdate, AdminUserCreate
from ...schemas.download import DownloadStats
from ...services.downloader import get_downloader_service
from ...services.plex_manager import get_plex_manager_service
from ...services.ai_agent import get_ai_agent_service
from ...config import get_settings
from ...logging_config import InMemoryLogHandler, get_available_modules, LOG_MODULES
from .auth import get_current_admin

router = APIRouter(prefix="/admin", tags=["Admin"])
settings = get_settings()
ph = PasswordHasher()


# =========================================================================
# USER MANAGEMENT
# =========================================================================

@router.get("/users", response_model=List[UserResponse])
async def list_users(
    status: Optional[UserStatus] = None,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Lister tous les utilisateurs. Optionally filter by status."""
    query = select(User).order_by(User.created_at.desc())
    if status:
        query = query.where(User.status == status)
    result = await db.execute(query)
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]


@router.get("/users/pending", response_model=List[UserResponse])
async def list_pending_users(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Lister les utilisateurs en attente d'approbation."""
    result = await db.execute(
        select(User).where(User.status == UserStatus.PENDING).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    user_data: AdminUserCreate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Créer un nouvel utilisateur (admin only). User is created as ACTIVE."""
    # Check if username exists
    result = await db.execute(
        select(User).where(User.username == user_data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Nom d'utilisateur déjà pris"
        )
    
    # Check if email exists
    if user_data.email:
        result = await db.execute(
            select(User).where(User.email == user_data.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="Email déjà utilisé"
            )
    
    # Create user with optional password
    hashed_pw = None
    if user_data.password:
        hashed_pw = ph.hash(user_data.password)
    
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_pw,
        role=user_data.role,
        status=user_data.status  # Admin-created users default to ACTIVE
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return UserResponse.model_validate(user)


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
    if update_data.status is not None:
        user.status = update_data.status
    
    await db.commit()
    await db.refresh(user)
    
    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/approve", response_model=UserResponse)
async def approve_user(
    user_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Approuver un utilisateur en attente."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    if user.status != UserStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"L'utilisateur n'est pas en attente (statut: {user.status.value})"
        )
    
    user.status = UserStatus.ACTIVE
    await db.commit()
    await db.refresh(user)
    
    # TODO: Send notification to user
    
    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/reject")
async def reject_user(
    user_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Rejeter/désactiver un utilisateur."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    if user.id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Vous ne pouvez pas vous désactiver vous-même"
        )
    
    user.status = UserStatus.DISABLED
    user.is_active = False
    await db.commit()
    
    return {"message": "Utilisateur désactivé"}


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
    """
    Obtenir les statistiques globales.
    Optimisé: les stats DB sont retournées immédiatement,
    les stats qBittorrent sont en cache ou avec timeout court.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    
    # User count - fast DB query
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar()
    
    # Request counts by status - single optimized query
    request_stats = {}
    for status in RequestStatus:
        count = (await db.execute(
            select(func.count()).where(MediaRequest.status == status)
        )).scalar()
        request_stats[status.value] = count
    
    total_requests = sum(request_stats.values())
    
    # Download info - run in thread pool with timeout to avoid blocking
    disk_usage = {}
    active_count = 0
    
    try:
        loop = asyncio.get_event_loop()
        downloader = get_downloader_service()
        
        with ThreadPoolExecutor() as executor:
            # Run with 2 second timeout
            disk_future = loop.run_in_executor(executor, downloader.get_disk_usage)
            try:
                disk_usage = await asyncio.wait_for(disk_future, timeout=2.0)
            except asyncio.TimeoutError:
                disk_usage = {}
            
            torrents_future = loop.run_in_executor(executor, downloader.get_all_torrents)
            try:
                torrents = await asyncio.wait_for(torrents_future, timeout=2.0)
                active_count = len(torrents)
            except asyncio.TimeoutError:
                active_count = 0
    except Exception:
        pass
    
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
            "active_count": active_count
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
    """
    Vérifier l'état de tous les services.
    Optimisé: exécution parallèle avec timeouts courts.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    
    plex = get_plex_manager_service()
    downloader = get_downloader_service()
    ai = get_ai_agent_service()
    
    # Run health checks in parallel with timeouts
    loop = asyncio.get_event_loop()
    
    async def check_with_timeout(coro_or_func, timeout=2.0, is_sync=False):
        try:
            if is_sync:
                with ThreadPoolExecutor() as executor:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(executor, coro_or_func),
                        timeout=timeout
                    )
            else:
                result = await asyncio.wait_for(coro_or_func, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            return {"status": "timeout"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    # Run all health checks in parallel
    plex_result, qbit_result, ollama_result = await asyncio.gather(
        check_with_timeout(plex.health_check, is_sync=True),
        check_with_timeout(downloader.health_check, is_sync=True),
        check_with_timeout(ai.health_check(), is_sync=False),
        return_exceptions=True
    )
    
    # Handle exceptions from gather
    if isinstance(plex_result, Exception):
        plex_result = {"status": "error", "message": str(plex_result)}
    if isinstance(qbit_result, Exception):
        qbit_result = {"status": "error", "message": str(qbit_result)}
    if isinstance(ollama_result, Exception):
        ollama_result = False
    
    return {
        "plex": plex_result,
        "qbittorrent": qbit_result,
        "ollama": {
            "status": "ok" if ollama_result is True else "error"
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


# =========================================================================
# PATH SETTINGS
# =========================================================================

@router.get("/settings/paths")
async def get_path_settings(
    current_user: User = Depends(get_current_admin)
):
    """
    Obtenir la configuration des chemins (download_path, library_paths).
    Retourne les chemins avec leur état de validation.
    """
    from ...services.settings_service import get_settings_service
    
    service = get_settings_service()
    return service.get_all_path_settings()


@router.put("/settings/paths")
async def update_path_settings(
    download_path: str = Query(..., description="Chemin de téléchargement"),
    library_paths: str = Query(..., description="JSON des chemins de librairie"),
    current_user: User = Depends(get_current_admin)
):
    """
    Mettre à jour la configuration des chemins.
    Sauvegarde en base de données.
    """
    import json
    from ...services.settings_service import get_settings_service
    
    # Parse library_paths from JSON string
    try:
        parsed_library_paths = json.loads(library_paths)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON for library_paths: {str(e)}"
        )
    
    service = get_settings_service()
    result = service.update_all_path_settings(download_path, parsed_library_paths)
    
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("errors", ["Erreur de validation"])
        )
    
    return result


@router.get("/filesystem/browse")
async def browse_filesystem(
    path: str = Query("/", description="Chemin du dossier à parcourir"),
    current_user: User = Depends(get_current_admin)
):
    """
    Parcourir le système de fichiers pour le file browser.
    Retourne uniquement les dossiers (pas les fichiers).
    """
    from ...services.settings_service import get_settings_service
    
    service = get_settings_service()
    result = service.browse_directory(path)
    
    if result.get("error"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error")
        )
    
    return result


# =========================================================================
# LOGS
# =========================================================================


@router.get("/logs")
async def get_logs_overview(
    current_user: User = Depends(get_current_admin)
):
    """
    Obtenir un aperçu des modules de logs disponibles et statistiques.
    """
    stats = InMemoryLogHandler.get_stats()
    modules = get_available_modules()
    
    return {
        "modules": modules,
        "module_info": {
            module: {
                "name": module.capitalize(),
                "prefixes": prefixes,
                "stats": stats.get(module, {"total": 0, "errors": 0, "warnings": 0})
            }
            for module, prefixes in LOG_MODULES.items()
        },
        "stats": stats
    }


@router.get("/logs/{module}")
async def get_logs(
    module: str,
    level: Optional[str] = Query(None, description="Filter by log level: DEBUG, INFO, WARNING, ERROR"),
    search: Optional[str] = Query(None, description="Search in log messages"),
    limit: int = Query(100, ge=1, le=1000, description="Number of logs to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: User = Depends(get_current_admin)
):
    """
    Obtenir les logs d'un module spécifique avec filtrage.
    
    Modules disponibles: all, api, pipeline, services, database, other
    """
    available = get_available_modules()
    
    if module not in available:
        raise HTTPException(
            status_code=400,
            detail=f"Module invalide. Modules disponibles: {', '.join(available)}"
        )
    
    result = InMemoryLogHandler.get_logs(
        module=module,
        level=level,
        search=search,
        limit=limit,
        offset=offset
    )
    
    return result
