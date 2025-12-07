"""
Media request endpoints.
"""
import asyncio
import logging
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...models import get_db, User, MediaRequest, Download
from ...models.request import RequestStatus, MediaType
from ...schemas.request import (
    RequestCreate, RequestResponse, RequestUpdate,
    RequestListResponse, UserRequestStats
)
from ...services.notifications import get_notification_service
from ...services.plex_manager import get_plex_manager_service
from ...services.pipeline import process_request_async
from .auth import get_current_user, get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/requests", tags=["Requests"])
settings = get_settings()


def run_async_in_background(coro):
    """Run async coroutine in background."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(coro)
        else:
            loop.run_until_complete(coro)
    except RuntimeError:
        asyncio.run(coro)


async def process_request_background(request_id: int):
    """Background task to process a media request through the pipeline."""
    await process_request_async(request_id)


@router.post("", response_model=RequestResponse, status_code=201)
async def create_request(
    request_data: RequestCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Créer une nouvelle demande de média.
    
    Limite: 10 demandes par jour par utilisateur (admins exemptés).
    """
    # Check daily limit (admins are exempt)
    if not current_user.is_admin and not current_user.can_make_request(settings.max_requests_per_day):
        raise HTTPException(
            status_code=429,
            detail=f"Limite quotidienne atteinte ({settings.max_requests_per_day} demandes/jour)"
        )
    
    # Check if already requested or available
    result = await db.execute(
        select(MediaRequest).where(
            MediaRequest.external_id == request_data.external_id,
            MediaRequest.source == request_data.source,
            MediaRequest.status.notin_([RequestStatus.CANCELLED, RequestStatus.ERROR])
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        if existing.status == RequestStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail="Ce média est déjà disponible"
            )
        raise HTTPException(
            status_code=400,
            detail="Ce média a déjà été demandé et est en cours de traitement"
        )
    
    # Check Plex availability
    plex_service = get_plex_manager_service()
    plex_check = plex_service.check_exists(
        title=request_data.title,
        year=request_data.year,
        media_type=request_data.media_type.value
    )
    
    if plex_check.get("exists"):
        raise HTTPException(
            status_code=400,
            detail=f"Ce média est déjà disponible sur Plex: {plex_check.get('plex_title')}"
        )
    
    # Create request
    media_request = MediaRequest(
        user_id=current_user.id,
        media_type=request_data.media_type,
        external_id=request_data.external_id,
        source=request_data.source,
        title=request_data.title,
        original_title=request_data.original_title,
        year=request_data.year,
        poster_url=request_data.poster_url,
        overview=request_data.overview,
        quality_preference=request_data.quality_preference,
        seasons_requested=request_data.seasons_requested,
        status=RequestStatus.PENDING
    )
    
    db.add(media_request)
    
    # Increment user's daily count
    current_user.increment_request_count()
    
    await db.commit()
    await db.refresh(media_request)
    
    # Send notification
    notification_service = get_notification_service()
    await notification_service.notify_request_created(
        title=media_request.title,
        media_type=media_request.media_type.value,
        username=current_user.username,
        poster_url=media_request.poster_url
    )
    
    # Start background processing
    background_tasks.add_task(process_request_background, media_request.id)
    
    return RequestResponse(
        id=media_request.id,
        user_id=current_user.id,
        username=current_user.username,
        media_type=media_request.media_type,
        external_id=media_request.external_id,
        source=media_request.source,
        title=media_request.title,
        original_title=media_request.original_title,
        year=media_request.year,
        poster_url=media_request.poster_url,
        overview=media_request.overview,
        quality_preference=media_request.quality_preference,
        seasons_requested=media_request.seasons_requested,
        status=media_request.status,
        status_message=media_request.status_message,
        created_at=media_request.created_at,
        updated_at=media_request.updated_at,
        completed_at=media_request.completed_at
    )


@router.get("", response_model=RequestListResponse)
async def list_requests(
    status: Optional[RequestStatus] = Query(None),
    media_type: Optional[MediaType] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Lister les demandes.
    
    Les utilisateurs voient leurs propres demandes.
    Les admins peuvent voir toutes les demandes.
    """
    query = select(MediaRequest)
    
    # Non-admin users only see their requests
    if not current_user.is_admin:
        query = query.where(MediaRequest.user_id == current_user.id)
    
    # Filters
    if status:
        query = query.where(MediaRequest.status == status)
    if media_type:
        query = query.where(MediaRequest.media_type == media_type)
    
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()
    
    # Pagination
    query = query.order_by(MediaRequest.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    requests = result.scalars().all()
    
    # Build response with usernames
    items = []
    for req in requests:
        # Load user
        user_result = await db.execute(select(User).where(User.id == req.user_id))
        user = user_result.scalar_one()
        
        items.append(RequestResponse(
            id=req.id,
            user_id=req.user_id,
            username=user.username,
            media_type=req.media_type,
            external_id=req.external_id,
            source=req.source,
            title=req.title,
            original_title=req.original_title,
            year=req.year,
            poster_url=req.poster_url,
            overview=req.overview,
            quality_preference=req.quality_preference,
            seasons_requested=req.seasons_requested,
            status=req.status,
            status_message=req.status_message,
            created_at=req.created_at,
            updated_at=req.updated_at,
            completed_at=req.completed_at
        ))
    
    return RequestListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )


@router.get("/me")
async def get_my_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Obtenir les demandes de l'utilisateur courant.
    
    Format simplifié pour le frontend.
    """
    query = select(MediaRequest).where(
        MediaRequest.user_id == current_user.id
    ).order_by(MediaRequest.created_at.desc())
    
    result = await db.execute(query)
    requests = result.scalars().all()
    
    return {
        "requests": [
            {
                "id": str(req.id),
                "media_type": req.media_type.value if req.media_type else "movie",
                "title": req.title,
                "year": req.year,
                "poster_url": req.poster_url,
                "status": req.status.value if req.status else "pending",
                "progress": getattr(req, 'progress', 0) or 0,
                "created_at": req.created_at.isoformat() if req.created_at else None
            }
            for req in requests
        ]
    }


@router.get("/stats", response_model=UserRequestStats)
async def get_my_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Obtenir les statistiques de demandes de l'utilisateur courant."""
    # Total requests
    total_query = select(func.count()).where(MediaRequest.user_id == current_user.id)
    total = (await db.execute(total_query)).scalar()
    
    # Pending
    pending_query = select(func.count()).where(
        MediaRequest.user_id == current_user.id,
        MediaRequest.status.in_([RequestStatus.PENDING, RequestStatus.SEARCHING, RequestStatus.DOWNLOADING])
    )
    pending = (await db.execute(pending_query)).scalar()
    
    # Completed
    completed_query = select(func.count()).where(
        MediaRequest.user_id == current_user.id,
        MediaRequest.status == RequestStatus.COMPLETED
    )
    completed = (await db.execute(completed_query)).scalar()
    
    # Today's requests
    today_count = current_user.daily_requests_count if current_user.last_request_date == date.today() else 0
    
    return UserRequestStats(
        total_requests=total,
        pending_requests=pending,
        completed_requests=completed,
        requests_today=today_count,
        requests_remaining=settings.max_requests_per_day - today_count
    )


@router.get("/{request_id}", response_model=RequestResponse)
async def get_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Obtenir les détails d'une demande."""
    result = await db.execute(
        select(MediaRequest).where(MediaRequest.id == request_id)
    )
    request = result.scalar_one_or_none()
    
    if not request:
        raise HTTPException(status_code=404, detail="Demande non trouvée")
    
    # Check access
    if not current_user.is_admin and request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Accès refusé")
    
    # Get username
    user_result = await db.execute(select(User).where(User.id == request.user_id))
    user = user_result.scalar_one()
    
    return RequestResponse(
        id=request.id,
        user_id=request.user_id,
        username=user.username,
        media_type=request.media_type,
        external_id=request.external_id,
        source=request.source,
        title=request.title,
        original_title=request.original_title,
        year=request.year,
        poster_url=request.poster_url,
        overview=request.overview,
        quality_preference=request.quality_preference,
        seasons_requested=request.seasons_requested,
        status=request.status,
        status_message=request.status_message,
        created_at=request.created_at,
        updated_at=request.updated_at,
        completed_at=request.completed_at
    )


@router.delete("/{request_id}")
async def delete_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Supprimer ou annuler une demande.
    
    - Admin: peut supprimer définitivement toute demande non-complétée
    - Utilisateur: peut annuler ses propres demandes en attente
    """
    result = await db.execute(
        select(MediaRequest).where(MediaRequest.id == request_id)
    )
    request = result.scalar_one_or_none()
    
    if not request:
        raise HTTPException(status_code=404, detail="Demande non trouvée")
    
    # Check access
    if not current_user.is_admin and request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Accès refusé")
    
    # Admin can delete any non-completed request permanently
    if current_user.is_admin:
        if request.status == RequestStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail="Impossible de supprimer une demande complétée"
            )
        
        # Delete related downloads first
        downloads_result = await db.execute(
            select(Download).where(Download.request_id == request_id)
        )
        for download in downloads_result.scalars().all():
            await db.delete(download)
        
        # Permanently delete the request
        await db.delete(request)
        await db.commit()
        logger.info(f"Request {request_id} ({request.title}) permanently deleted by admin {current_user.username}")
        return {"message": "Demande supprimée définitivement"}
    
    # Regular users can only cancel pending/searching requests
    if request.status not in [RequestStatus.PENDING, RequestStatus.SEARCHING, RequestStatus.AWAITING_APPROVAL]:
        raise HTTPException(
            status_code=400,
            detail="Cette demande ne peut plus être annulée"
        )
    
    request.status = RequestStatus.CANCELLED
    request.status_message = f"Annulé par {current_user.username}"
    await db.commit()
    
    return {"message": "Demande annulée"}


@router.post("/{request_id}/approve")
async def approve_request(
    request_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Approuver une demande en attente de validation (admin uniquement)."""
    result = await db.execute(
        select(MediaRequest).where(MediaRequest.id == request_id)
    )
    request = result.scalar_one_or_none()
    
    if not request:
        raise HTTPException(status_code=404, detail="Demande non trouvée")
    
    if request.status != RequestStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail="Cette demande n'est pas en attente d'approbation"
        )
    
    request.status = RequestStatus.PENDING
    request.status_message = f"Approuvé par {current_user.username}"
    await db.commit()
    
    # TODO: Restart processing
    
    return {"message": "Demande approuvée"}


@router.patch("/{request_id}", response_model=RequestResponse)
async def update_request(
    request_id: int,
    update_data: RequestUpdate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Mettre à jour une demande (admin uniquement)."""
    result = await db.execute(
        select(MediaRequest).where(MediaRequest.id == request_id)
    )
    request = result.scalar_one_or_none()
    
    if not request:
        raise HTTPException(status_code=404, detail="Demande non trouvée")
    
    if update_data.status:
        request.status = update_data.status
    if update_data.status_message:
        request.status_message = update_data.status_message
    if update_data.quality_preference:
        request.quality_preference = update_data.quality_preference
    
    await db.commit()
    await db.refresh(request)
    
    # Get username
    user_result = await db.execute(select(User).where(User.id == request.user_id))
    user = user_result.scalar_one()
    
    return RequestResponse(
        id=request.id,
        user_id=request.user_id,
        username=user.username,
        media_type=request.media_type,
        external_id=request.external_id,
        source=request.source,
        title=request.title,
        original_title=request.original_title,
        year=request.year,
        poster_url=request.poster_url,
        overview=request.overview,
        quality_preference=request.quality_preference,
        seasons_requested=request.seasons_requested,
        status=request.status,
        status_message=request.status_message,
        created_at=request.created_at,
        updated_at=request.updated_at,
        completed_at=request.completed_at
    )
