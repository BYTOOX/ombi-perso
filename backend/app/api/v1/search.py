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
from ...config import get_settings

router = APIRouter(prefix="/search", tags=["Search"])
settings = get_settings()


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


@router.get("/trending")
async def get_trending(
    type: str = Query("movie", description="Type: movie or tv"),
    current_user: User = Depends(get_current_user),
    search_service: MediaSearchService = Depends(get_media_search_service)
):
    """
    Obtenir les médias tendances (TMDB trending).
    
    Utilisé pour la page d'accueil (hero et rows).
    """
    import httpx
    
    if not settings.tmdb_api_key:
        return {"results": []}
    
    media_type = "movie" if type == "movie" else "tv"
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"https://api.themoviedb.org/3/trending/{media_type}/week",
                params={
                    "api_key": settings.tmdb_api_key,
                    "language": "fr-FR"
                }
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get("results", [])[:20]:
                is_movie = media_type == "movie"
                
                # Extract date safely
                date_field = item.get("release_date" if is_movie else "first_air_date") or ""
                year = int(date_field.split("-")[0]) if date_field and "-" in date_field else None
                
                results.append({
                    "id": str(item["id"]),
                    "source": "tmdb",
                    "media_type": "movie" if is_movie else "series",
                    "title": item.get("title" if is_movie else "name", "Unknown"),
                    "original_title": item.get("original_title" if is_movie else "original_name"),
                    "year": year,
                    "poster_url": f"https://image.tmdb.org/t/p/w500{item['poster_path']}" if item.get("poster_path") else None,
                    "backdrop_url": f"https://image.tmdb.org/t/p/original{item['backdrop_path']}" if item.get("backdrop_path") else None,
                    "overview": item.get("overview"),
                    "rating": item.get("vote_average"),
                    "vote_count": item.get("vote_count"),
                    "genres": []
                })
            
            return {"results": results}
            
    except Exception as e:
        import logging
        logging.error(f"Trending fetch error: {e}")
        return {"results": []}
