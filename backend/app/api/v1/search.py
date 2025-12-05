"""
Search endpoints for media discovery.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException

from ...services.media_search import MediaSearchService, get_media_search_service
from ...services.plex_manager import PlexManagerService, get_plex_manager_service
from ...schemas.media import MediaSearchResult, MediaDetails, MediaType
from .auth import get_current_user
from ...models import User

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("", response_model=List[MediaSearchResult])
async def search_media(
    q: str = Query(..., min_length=2, description="Terme de recherche"),
    type: MediaType = Query(MediaType.ALL, description="Type de média"),
    year: Optional[int] = Query(None, ge=1900, le=2030, description="Année"),
    page: int = Query(1, ge=1, le=100, description="Numéro de page"),
    current_user: User = Depends(get_current_user),
    search_service: MediaSearchService = Depends(get_media_search_service),
    plex_service: PlexManagerService = Depends(get_plex_manager_service)
):
    """
    Recherche unifiée de médias.
    
    Retourne des résultats de TMDB (films/séries) et AniList (animés).
    """
    results = await search_service.search(
        query=q,
        media_type=type.value,
        year=year,
        page=page
    )
    
    # Check availability on Plex
    for result in results:
        plex_check = plex_service.check_exists(
            title=result.title,
            year=result.year,
            media_type=result.media_type
        )
        result.already_available = plex_check.get("exists", False)
        if plex_check.get("rating_key"):
            result.plex_rating_key = plex_check.get("rating_key")
    
    return results


@router.get("/{source}/{media_id}", response_model=MediaDetails)
async def get_media_details(
    source: str,
    media_id: str,
    media_type: str = Query("movie", description="Type de média (movie, series, anime)"),
    current_user: User = Depends(get_current_user),
    search_service: MediaSearchService = Depends(get_media_search_service)
):
    """
    Obtenir les détails d'un média spécifique.
    
    - source: "tmdb" ou "anilist"
    - media_id: ID externe du média
    """
    if source not in ("tmdb", "anilist"):
        raise HTTPException(status_code=400, detail="Source invalide")
    
    details = await search_service.get_details(
        external_id=media_id,
        source=source,
        media_type=media_type
    )
    
    if not details:
        raise HTTPException(status_code=404, detail="Média non trouvé")
    
    return details


@router.get("/torrents/{media_type}")
async def search_torrents(
    media_type: str,
    query: str = Query(..., min_length=2),
    page: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user)
):
    """
    Recherche de torrents sur YGGtorrent.
    Nécessite FlareSolverr pour le bypass Cloudflare.
    """
    from ...services.torrent_scraper import get_torrent_scraper_service
    
    scraper = get_torrent_scraper_service()
    results = await scraper.search(
        query=query,
        media_type=media_type,
        page=page
    )
    
    return {"results": results, "count": len(results)}
