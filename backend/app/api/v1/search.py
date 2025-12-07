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


@router.get("/discover")
async def discover_media(
    type: str = Query("movie", description="Type: movie, tv, or anime"),
    category: str = Query("top_rated", description="Category: top_rated, classics, hidden_gems, random"),
    current_user: User = Depends(get_current_user),
    search_service: MediaSearchService = Depends(get_media_search_service)
):
    """
    Discover media by curated categories.
    
    Categories:
    - top_rated: Best rated released films/shows
    - classics: Cult classics (before 2000 for movies, 2010 for TV)
    - hidden_gems: High rating but low popularity
    - random: Random selection for discovery
    """
    import httpx
    import random
    from datetime import date
    
    if not settings.tmdb_api_key:
        return {"results": []}
    
    # Handle anime separately via AniList
    if type == "anime":
        return await _discover_anime(category, search_service)
    
    media_type = "movie" if type == "movie" else "tv"
    is_movie = media_type == "movie"
    today = date.today().isoformat()
    
    # Build query params based on category
    params = {
        "api_key": settings.tmdb_api_key,
        "language": "fr-FR",
        "sort_by": "vote_average.desc",
        "include_adult": "false",
        "include_video": "false",
        "page": 1
    }
    
    # Exclude animation genre for TV (to avoid anime pollution)
    # Genre 16 = Animation in TMDB
    if not is_movie:
        params["without_genres"] = "16"
    
    if category == "top_rated":
        # Best rated, already released, with enough votes
        params["vote_count.gte"] = 1000
        params["vote_average.gte"] = 7.0
        if is_movie:
            params["primary_release_date.lte"] = today
        else:
            params["first_air_date.lte"] = today
            
    elif category == "classics":
        # Older content with high ratings
        params["vote_count.gte"] = 3000
        params["vote_average.gte"] = 7.5
        if is_movie:
            params["primary_release_date.lte"] = "2005-01-01"
            params["primary_release_date.gte"] = "1970-01-01"
        else:
            params["first_air_date.lte"] = "2015-01-01"
            params["first_air_date.gte"] = "1990-01-01"
            
    elif category == "hidden_gems":
        # Good rating but not mainstream
        params["vote_count.gte"] = 100
        params["vote_count.lte"] = 2000
        params["vote_average.gte"] = 7.0
        params["sort_by"] = "vote_average.desc"
        if is_movie:
            params["primary_release_date.lte"] = today
        else:
            params["first_air_date.lte"] = today
            
    elif category == "random":
        # Random page for variety
        params["page"] = random.randint(1, 20)
        params["vote_count.gte"] = 500
        params["vote_average.gte"] = 6.0
        params["sort_by"] = "popularity.desc"
        if is_movie:
            params["primary_release_date.lte"] = today
        else:
            params["first_air_date.lte"] = today
    
    # === MOVIE-SPECIFIC CATEGORIES ===
    elif category == "blockbusters" and is_movie:
        # Action blockbusters - Genre 28 = Action
        params["with_genres"] = "28"
        params["vote_count.gte"] = 2000
        params["vote_average.gte"] = 6.5
        params["sort_by"] = "popularity.desc"
        params["primary_release_date.lte"] = today
        params["primary_release_date.gte"] = "2015-01-01"
        
    elif category == "comedy" and is_movie:
        # Comedy - Genre 35 = Comedy
        params["with_genres"] = "35"
        params["vote_count.gte"] = 500
        params["vote_average.gte"] = 6.5
        params["sort_by"] = "vote_average.desc"
        params["primary_release_date.lte"] = today
        
    elif category == "thriller" and is_movie:
        # Thriller/Horror - Genres 53 = Thriller, 27 = Horror
        params["with_genres"] = "53|27"
        params["vote_count.gte"] = 500
        params["vote_average.gte"] = 6.5
        params["sort_by"] = "vote_average.desc"
        params["primary_release_date.lte"] = today
        
    elif category == "award_winners" and is_movie:
        # Highly acclaimed films (simulated award winners) - different from top_rated
        params["vote_count.gte"] = 8000  # Even more votes = proven classics
        params["vote_average.gte"] = 7.8
        params["sort_by"] = "vote_count.desc"  # Most voted = most recognized
        params["primary_release_date.lte"] = "2020-01-01"  # Older acclaimed films
        params["page"] = 2  # Page 2 for different results
    
    # === TV-SPECIFIC CATEGORIES ===
    elif category == "binge" and not is_movie:
        # Binge-worthy - highly rated, popular
        params["vote_count.gte"] = 1000
        params["vote_average.gte"] = 8.0
        params["sort_by"] = "vote_average.desc"
        params["first_air_date.lte"] = today
        
    elif category == "miniseries" and not is_movie:
        # Use Drama genre as proxy (TMDB doesn't have miniseries filter)
        params["with_genres"] = "18"  # Drama
        params["vote_count.gte"] = 500
        params["vote_average.gte"] = 7.5
        params["sort_by"] = "vote_average.desc"
        params["first_air_date.lte"] = today
        
    elif category == "airing" and not is_movie:
        # Currently popular (proxy for airing)
        params["sort_by"] = "popularity.desc"
        params["vote_count.gte"] = 100
        params["first_air_date.gte"] = "2024-01-01"
        params["first_air_date.lte"] = today
        
    elif category == "crime" and not is_movie:
        # Crime/Thriller - Genre 80 = Crime, 9648 = Mystery
        params["with_genres"] = "80|9648"
        params["vote_count.gte"] = 500
        params["vote_average.gte"] = 7.0
        params["sort_by"] = "vote_average.desc"
        params["first_air_date.lte"] = today
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"https://api.themoviedb.org/3/discover/{media_type}",
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            items = data.get("results", [])[:20]
            
            # Shuffle for random category
            if category == "random":
                random.shuffle(items)
            
            for item in items:
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
            
            return {"results": results, "category": category, "type": type}
            
    except Exception as e:
        import logging
        logging.error(f"Discover fetch error: {e}")
        return {"results": [], "category": category, "type": type}


@router.get("/hero")
async def get_hero_media(
    type: str = Query("movie", description="Type: movie, tv, or anime"),
    current_user: User = Depends(get_current_user),
    search_service: MediaSearchService = Depends(get_media_search_service)
):
    """
    Get a random high-rated media for hero section.
    Returns a different item on each call.
    """
    import httpx
    import random
    from datetime import date
    
    if not settings.tmdb_api_key:
        return None
    
    # Handle anime separately
    if type == "anime":
        return await _get_anime_hero(search_service)
    
    media_type = "movie" if type == "movie" else "tv"
    is_movie = media_type == "movie"
    today = date.today().isoformat()
    
    params = {
        "api_key": settings.tmdb_api_key,
        "language": "fr-FR",
        "sort_by": "vote_average.desc",
        "vote_count.gte": 2000,
        "vote_average.gte": 7.5,
        "page": random.randint(1, 5),  # Random page for variety
    }
    
    if is_movie:
        params["primary_release_date.lte"] = today
        params["primary_release_date.gte"] = "2010-01-01"  # Recent enough for good images
    else:
        params["first_air_date.lte"] = today
        params["first_air_date.gte"] = "2010-01-01"
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"https://api.themoviedb.org/3/discover/{media_type}",
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            items = data.get("results", [])
            # Filter items with backdrop images
            items = [i for i in items if i.get("backdrop_path")]
            
            if not items:
                return None
            
            # Pick random item
            item = random.choice(items)
            
            date_field = item.get("release_date" if is_movie else "first_air_date") or ""
            year = int(date_field.split("-")[0]) if date_field and "-" in date_field else None
            
            return {
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
            }
            
    except Exception as e:
        import logging
        logging.error(f"Hero fetch error: {e}")
        return None


async def _discover_anime(category: str, search_service: MediaSearchService):
    """Discover anime via AniList + US animated series from TMDB."""
    import httpx
    import random
    from datetime import date
    
    results = []
    
    # 1. Fetch from AniList (Japanese anime)
    # Use genre_in for anime-specific categories
    anilist_query = """
    query ($page: Int, $perPage: Int, $sort: [MediaSort], $averageScoreGreater: Int, $popularityLesser: Int, $genre_in: [String]) {
        Page(page: $page, perPage: $perPage) {
            media(type: ANIME, sort: $sort, averageScore_greater: $averageScoreGreater, popularity_lesser: $popularityLesser, genre_in: $genre_in, status_in: [FINISHED, RELEASING]) {
                id
                title {
                    romaji
                    english
                    native
                }
                coverImage {
                    large
                    extraLarge
                }
                bannerImage
                description
                averageScore
                popularity
                startDate {
                    year
                }
                genres
            }
        }
    }
    """
    
    variables = {"page": 1, "perPage": 12}
    
    if category == "top_rated":
        variables["sort"] = ["SCORE_DESC"]
        variables["averageScoreGreater"] = 80
    elif category == "classics":
        # Classics - use favorites sort and page 2 for different results
        variables["sort"] = ["FAVOURITES_DESC"]
        variables["averageScoreGreater"] = 75
        variables["page"] = 2  # Different page for variety
    elif category == "hidden_gems":
        variables["sort"] = ["SCORE_DESC"]
        variables["averageScoreGreater"] = 70
        variables["popularityLesser"] = 50000
    elif category == "random":
        variables["sort"] = ["POPULARITY_DESC"]
        variables["page"] = random.randint(1, 10)
    
    # === ANIME-SPECIFIC CATEGORIES ===
    elif category == "shonen":
        # Action/Adventure anime (Shonen style)
        variables["sort"] = ["SCORE_DESC"]
        variables["genre_in"] = ["Action", "Adventure"]
        variables["averageScoreGreater"] = 70
    elif category == "romance":
        # Romance anime
        variables["sort"] = ["SCORE_DESC"]
        variables["genre_in"] = ["Romance"]
        variables["averageScoreGreater"] = 70
    elif category == "isekai":
        # Isekai/Fantasy anime
        variables["sort"] = ["POPULARITY_DESC"]
        variables["genre_in"] = ["Fantasy"]
        variables["averageScoreGreater"] = 65
    elif category == "psychological":
        # Psychological/Thriller anime
        variables["sort"] = ["SCORE_DESC"]
        variables["genre_in"] = ["Psychological", "Thriller"]
        variables["averageScoreGreater"] = 75
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # AniList request
            anilist_response = await client.post(
                "https://graphql.anilist.co",
                json={"query": anilist_query, "variables": variables}
            )
            anilist_response.raise_for_status()
            anilist_data = anilist_response.json()
            
            import logging
            logging.info(f"AniList response keys: {anilist_data.keys()}")
            
            items = anilist_data.get("data", {}).get("Page", {}).get("media", [])
            logging.info(f"AniList items count: {len(items)}")
            
            for item in items:
                title = item.get("title", {})
                results.append({
                    "id": str(item["id"]),
                    "source": "anilist",
                    "media_type": "anime",
                    "title": title.get("english") or title.get("romaji") or "Unknown",
                    "original_title": title.get("native"),
                    "year": item.get("startDate", {}).get("year"),
                    "poster_url": item.get("coverImage", {}).get("extraLarge") or item.get("coverImage", {}).get("large"),
                    "backdrop_url": item.get("bannerImage"),
                    "overview": item.get("description", "").replace("<br>", " ").replace("<i>", "").replace("</i>", "")[:500] if item.get("description") else None,
                    "rating": (item.get("averageScore") or 0) / 10,
                    "vote_count": item.get("popularity"),
                    "genres": item.get("genres", [])
                })
            
            # 2. Fetch from TMDB (US/Western animated series)
            today = date.today().isoformat()
            tmdb_params = {
                "api_key": settings.tmdb_api_key,
                "language": "fr-FR",
                "with_genres": "16",  # Animation genre only
                "sort_by": "vote_average.desc",
                "vote_count.gte": 500,
                "vote_average.gte": 7.0,
                "first_air_date.lte": today,
                "page": 1
            }
            
            if category == "classics":
                tmdb_params["first_air_date.lte"] = "2015-01-01"
                tmdb_params["first_air_date.gte"] = "1990-01-01"
            elif category == "hidden_gems":
                tmdb_params["vote_count.gte"] = 100
                tmdb_params["vote_count.lte"] = 1000
            elif category == "random":
                tmdb_params["page"] = random.randint(1, 5)
                tmdb_params["sort_by"] = "popularity.desc"
            
            tmdb_response = await client.get(
                "https://api.themoviedb.org/3/discover/tv",
                params=tmdb_params
            )
            tmdb_response.raise_for_status()
            tmdb_data = tmdb_response.json()
            
            for item in tmdb_data.get("results", [])[:8]:  # Limit TMDB results
                date_field = item.get("first_air_date") or ""
                year = int(date_field.split("-")[0]) if date_field and "-" in date_field else None
                
                results.append({
                    "id": str(item["id"]),
                    "source": "tmdb",
                    "media_type": "anime",  # Mark as anime for consistency
                    "title": item.get("name", "Unknown"),
                    "original_title": item.get("original_name"),
                    "year": year,
                    "poster_url": f"https://image.tmdb.org/t/p/w500{item['poster_path']}" if item.get("poster_path") else None,
                    "backdrop_url": f"https://image.tmdb.org/t/p/original{item['backdrop_path']}" if item.get("backdrop_path") else None,
                    "overview": item.get("overview"),
                    "rating": item.get("vote_average"),
                    "vote_count": item.get("vote_count"),
                    "genres": []
                })
            
            # Shuffle results to mix anime and animated series
            if category == "random":
                random.shuffle(results)
            
            return {"results": results, "category": category, "type": "anime"}
            
    except Exception as e:
        import logging
        logging.error(f"Anime discover error: {e}")
        return {"results": results if results else [], "category": category, "type": "anime"}


async def _get_anime_hero(search_service: MediaSearchService):
    """Get random high-rated anime for hero section."""
    import httpx
    import random
    
    query = """
    query ($page: Int, $perPage: Int) {
        Page(page: $page, perPage: $perPage) {
            media(type: ANIME, sort: SCORE_DESC, averageScore_greater: 85, status_in: [FINISHED, RELEASING]) {
                id
                title {
                    romaji
                    english
                    native
                }
                coverImage {
                    large
                    extraLarge
                }
                bannerImage
                description
                averageScore
                popularity
                startDate {
                    year
                }
                genres
            }
        }
    }
    """
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://graphql.anilist.co",
                json={"query": query, "variables": {"page": random.randint(1, 3), "perPage": 20}}
            )
            response.raise_for_status()
            data = response.json()
            
            items = data.get("data", {}).get("Page", {}).get("media", [])
            # Filter for items with banner images
            items = [i for i in items if i.get("bannerImage")]
            
            if not items:
                return None
            
            item = random.choice(items)
            title = item.get("title", {})
            
            return {
                "id": str(item["id"]),
                "source": "anilist",
                "media_type": "anime",
                "title": title.get("english") or title.get("romaji") or "Unknown",
                "original_title": title.get("native"),
                "year": item.get("startDate", {}).get("year"),
                "poster_url": item.get("coverImage", {}).get("extraLarge") or item.get("coverImage", {}).get("large"),
                "backdrop_url": item.get("bannerImage"),
                "overview": item.get("description", "").replace("<br>", " ").replace("<i>", "").replace("</i>", "")[:500] if item.get("description") else None,
                "rating": (item.get("averageScore") or 0) / 10,
                "vote_count": item.get("popularity"),
                "genres": item.get("genres", [])
            }
            
    except Exception as e:
        import logging
        logging.error(f"AniList hero error: {e}")
        return None

