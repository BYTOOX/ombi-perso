"""
Media search service integrating TMDB and AniList.
"""
import httpx
from typing import List, Optional, Dict, Any
from functools import lru_cache
import logging

from ..config import get_settings
from ..schemas.media import MediaSearchResult, MediaDetails, MediaSource

logger = logging.getLogger(__name__)


class MediaSearchService:
    """Unified media search across TMDB and AniList."""
    
    TMDB_BASE_URL = "https://api.themoviedb.org/3"
    TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"
    ANILIST_API_URL = "https://graphql.anilist.co"
    
    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    # =========================================================================
    # UNIFIED SEARCH
    # =========================================================================
    
    async def search(
        self,
        query: str,
        media_type: str = "all",
        year: Optional[int] = None,
        page: int = 1
    ) -> List[MediaSearchResult]:
        """
        Search for media across all sources.
        
        Args:
            query: Search query
            media_type: "all", "movie", "series", "anime"
            year: Optional year filter
            page: Page number
            
        Returns:
            List of search results
        """
        results = []
        
        # Search TMDB for movies/series
        if media_type in ("all", "movie"):
            tmdb_movies = await self._search_tmdb(query, "movie", year, page)
            results.extend(tmdb_movies)
        
        if media_type in ("all", "series"):
            tmdb_series = await self._search_tmdb(query, "tv", year, page)
            results.extend(tmdb_series)
        
        # Search AniList for anime
        if media_type in ("all", "anime"):
            anime_results = await self._search_anilist(query, year, page)
            results.extend(anime_results)
        
        # Sort by popularity/rating
        results.sort(key=lambda x: x.vote_count or 0, reverse=True)
        
        return results
    
    async def get_details(
        self,
        external_id: str,
        source: str = "tmdb",
        media_type: str = "movie"
    ) -> Optional[MediaDetails]:
        """Get detailed info for a specific media."""
        if source == "tmdb":
            return await self._get_tmdb_details(external_id, media_type)
        elif source == "anilist":
            return await self._get_anilist_details(int(external_id))
        return None
    
    # =========================================================================
    # TMDB INTEGRATION
    # =========================================================================
    
    async def _search_tmdb(
        self,
        query: str,
        media_type: str,  # "movie" or "tv"
        year: Optional[int] = None,
        page: int = 1
    ) -> List[MediaSearchResult]:
        """Search TMDB."""
        if not self.settings.tmdb_api_key:
            logger.warning("TMDB API key not configured")
            return []
        
        params = {
            "api_key": self.settings.tmdb_api_key,
            "query": query,
            "page": page,
            "language": "fr-FR",
            "include_adult": False
        }
        
        if year:
            key = "year" if media_type == "movie" else "first_air_date_year"
            params[key] = year
        
        try:
            response = await self.client.get(
                f"{self.TMDB_BASE_URL}/search/{media_type}",
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            return [
                self._parse_tmdb_result(item, media_type)
                for item in data.get("results", [])
            ]
        except Exception as e:
            logger.error(f"TMDB search error: {e}")
            return []
    
    async def _get_tmdb_details(
        self,
        tmdb_id: str,
        media_type: str
    ) -> Optional[MediaDetails]:
        """Get TMDB details."""
        if not self.settings.tmdb_api_key:
            return None
        
        endpoint = "movie" if media_type == "movie" else "tv"
        params = {
            "api_key": self.settings.tmdb_api_key,
            "language": "fr-FR",
            "append_to_response": "credits,videos,recommendations,similar"
        }
        
        try:
            response = await self.client.get(
                f"{self.TMDB_BASE_URL}/{endpoint}/{tmdb_id}",
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            return self._parse_tmdb_details(data, media_type)
        except Exception as e:
            logger.error(f"TMDB details error: {e}")
            return None
    
    def _parse_tmdb_result(self, item: Dict[str, Any], media_type: str) -> MediaSearchResult:
        """Parse TMDB search result."""
        is_movie = media_type == "movie"
        
        return MediaSearchResult(
            id=str(item["id"]),
            source=MediaSource.TMDB,
            media_type="movie" if is_movie else "series",
            title=item.get("title" if is_movie else "name", "Unknown"),
            original_title=item.get("original_title" if is_movie else "original_name"),
            year=self._extract_year(item.get("release_date" if is_movie else "first_air_date")),
            poster_url=self._get_tmdb_image_url(item.get("poster_path"), "w500"),
            backdrop_url=self._get_tmdb_image_url(item.get("backdrop_path"), "original"),
            overview=item.get("overview"),
            rating=item.get("vote_average"),
            vote_count=item.get("vote_count"),
            genres=[]
        )
    
    def _parse_tmdb_details(self, data: Dict[str, Any], media_type: str) -> MediaDetails:
        """Parse TMDB details response."""
        is_movie = media_type == "movie"
        
        # Extract trailer
        trailer_url = None
        videos = data.get("videos", {}).get("results", [])
        for video in videos:
            if video.get("type") == "Trailer" and video.get("site") == "YouTube":
                trailer_url = f"https://www.youtube.com/watch?v={video['key']}"
                break
        
        return MediaDetails(
            id=str(data["id"]),
            source=MediaSource.TMDB,
            media_type="movie" if is_movie else "series",
            title=data.get("title" if is_movie else "name", "Unknown"),
            original_title=data.get("original_title" if is_movie else "original_name"),
            year=self._extract_year(data.get("release_date" if is_movie else "first_air_date")),
            poster_url=self._get_tmdb_image_url(data.get("poster_path"), "w500"),
            backdrop_url=self._get_tmdb_image_url(data.get("backdrop_path"), "original"),
            overview=data.get("overview"),
            rating=data.get("vote_average"),
            vote_count=data.get("vote_count"),
            genres=[g["name"] for g in data.get("genres", [])],
            seasons_count=data.get("number_of_seasons"),
            episodes_count=data.get("number_of_episodes"),
            status=data.get("status"),
            cast=[
                {"name": c["name"], "character": c.get("character"), "profile": self._get_tmdb_image_url(c.get("profile_path"), "w185")}
                for c in data.get("credits", {}).get("cast", [])[:10]
            ],
            crew=[
                {"name": c["name"], "job": c.get("job")}
                for c in data.get("credits", {}).get("crew", [])
                if c.get("job") in ("Director", "Writer", "Creator")
            ],
            trailer_url=trailer_url,
            similar=[
                self._parse_tmdb_result(s, media_type)
                for s in data.get("similar", {}).get("results", [])[:5]
            ],
            recommendations=[
                self._parse_tmdb_result(r, media_type)
                for r in data.get("recommendations", {}).get("results", [])[:5]
            ]
        )
    
    def _get_tmdb_image_url(self, path: Optional[str], size: str) -> Optional[str]:
        """Build TMDB image URL."""
        if not path:
            return None
        return f"{self.TMDB_IMAGE_BASE}/{size}{path}"
    
    # =========================================================================
    # ANILIST INTEGRATION (GraphQL)
    # =========================================================================
    
    async def _search_anilist(
        self,
        query: str,
        year: Optional[int] = None,
        page: int = 1
    ) -> List[MediaSearchResult]:
        """Search AniList for anime."""
        graphql_query = """
        query ($search: String, $page: Int, $perPage: Int, $seasonYear: Int) {
            Page(page: $page, perPage: $perPage) {
                media(search: $search, type: ANIME, seasonYear: $seasonYear, sort: POPULARITY_DESC) {
                    id
                    idMal
                    title {
                        romaji
                        english
                        native
                    }
                    startDate {
                        year
                    }
                    coverImage {
                        large
                        extraLarge
                    }
                    bannerImage
                    description
                    averageScore
                    popularity
                    episodes
                    status
                    genres
                    studios(isMain: true) {
                        nodes {
                            name
                        }
                    }
                }
            }
        }
        """
        
        variables = {
            "search": query,
            "page": page,
            "perPage": 20
        }
        if year:
            variables["seasonYear"] = year
        
        try:
            response = await self.client.post(
                self.ANILIST_API_URL,
                json={"query": graphql_query, "variables": variables}
            )
            response.raise_for_status()
            data = response.json()
            
            media_list = data.get("data", {}).get("Page", {}).get("media", [])
            return [self._parse_anilist_result(item) for item in media_list]
        except Exception as e:
            logger.error(f"AniList search error: {e}")
            return []
    
    async def _get_anilist_details(self, anilist_id: int) -> Optional[MediaDetails]:
        """Get AniList details."""
        graphql_query = """
        query ($id: Int) {
            Media(id: $id, type: ANIME) {
                id
                idMal
                title {
                    romaji
                    english
                    native
                }
                startDate {
                    year
                }
                coverImage {
                    large
                    extraLarge
                }
                bannerImage
                description
                averageScore
                popularity
                episodes
                status
                genres
                studios(isMain: true) {
                    nodes {
                        name
                    }
                }
                characters(role: MAIN, page: 1, perPage: 10) {
                    nodes {
                        name {
                            full
                        }
                    }
                }
                recommendations(page: 1, perPage: 5) {
                    nodes {
                        mediaRecommendation {
                            id
                            title {
                                romaji
                                english
                            }
                            coverImage {
                                large
                            }
                            averageScore
                        }
                    }
                }
                trailer {
                    id
                    site
                }
            }
        }
        """
        
        try:
            response = await self.client.post(
                self.ANILIST_API_URL,
                json={"query": graphql_query, "variables": {"id": anilist_id}}
            )
            response.raise_for_status()
            data = response.json()
            
            media = data.get("data", {}).get("Media")
            if not media:
                return None
            
            return self._parse_anilist_details(media)
        except Exception as e:
            logger.error(f"AniList details error: {e}")
            return None
    
    def _parse_anilist_result(self, item: Dict[str, Any]) -> MediaSearchResult:
        """Parse AniList search result."""
        title = item.get("title", {})
        
        return MediaSearchResult(
            id=str(item["id"]),
            source=MediaSource.ANILIST,
            media_type="anime",
            title=title.get("english") or title.get("romaji") or "Unknown",
            original_title=title.get("native"),
            romaji_title=title.get("romaji"),
            native_title=title.get("native"),
            year=item.get("startDate", {}).get("year"),
            poster_url=item.get("coverImage", {}).get("extraLarge") or item.get("coverImage", {}).get("large"),
            backdrop_url=item.get("bannerImage"),
            overview=self._clean_html(item.get("description")),
            rating=item.get("averageScore", 0) / 10 if item.get("averageScore") else None,
            vote_count=item.get("popularity"),
            episodes_count=item.get("episodes"),
            status=item.get("status"),
            genres=item.get("genres", []),
            studios=[s["name"] for s in item.get("studios", {}).get("nodes", [])]
        )
    
    def _parse_anilist_details(self, media: Dict[str, Any]) -> MediaDetails:
        """Parse AniList details."""
        title = media.get("title", {})
        
        # Extract trailer
        trailer = media.get("trailer")
        trailer_url = None
        if trailer and trailer.get("site") == "youtube":
            trailer_url = f"https://www.youtube.com/watch?v={trailer['id']}"
        
        return MediaDetails(
            id=str(media["id"]),
            source=MediaSource.ANILIST,
            media_type="anime",
            title=title.get("english") or title.get("romaji") or "Unknown",
            original_title=title.get("native"),
            romaji_title=title.get("romaji"),
            native_title=title.get("native"),
            year=media.get("startDate", {}).get("year"),
            poster_url=media.get("coverImage", {}).get("extraLarge"),
            backdrop_url=media.get("bannerImage"),
            overview=self._clean_html(media.get("description")),
            rating=media.get("averageScore", 0) / 10 if media.get("averageScore") else None,
            vote_count=media.get("popularity"),
            episodes_count=media.get("episodes"),
            status=media.get("status"),
            genres=media.get("genres", []),
            studios=[s["name"] for s in media.get("studios", {}).get("nodes", [])],
            mal_id=media.get("idMal"),
            anilist_id=media["id"],
            trailer_url=trailer_url,
            cast=[
                {"name": c.get("name", {}).get("full"), "character": None, "profile": None}
                for c in media.get("characters", {}).get("nodes", [])
            ],
            recommendations=[
                MediaSearchResult(
                    id=str(r.get("mediaRecommendation", {}).get("id")),
                    source=MediaSource.ANILIST,
                    media_type="anime",
                    title=r.get("mediaRecommendation", {}).get("title", {}).get("english") or 
                          r.get("mediaRecommendation", {}).get("title", {}).get("romaji") or "Unknown",
                    poster_url=r.get("mediaRecommendation", {}).get("coverImage", {}).get("large"),
                    rating=r.get("mediaRecommendation", {}).get("averageScore", 0) / 10 if r.get("mediaRecommendation", {}).get("averageScore") else None
                )
                for r in media.get("recommendations", {}).get("nodes", [])
                if r.get("mediaRecommendation")
            ]
        )
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    @staticmethod
    def _extract_year(date_str: Optional[str]) -> Optional[int]:
        """Extract year from date string."""
        if not date_str:
            return None
        try:
            return int(date_str.split("-")[0])
        except (ValueError, IndexError):
            return None
    
    @staticmethod
    def _clean_html(text: Optional[str]) -> Optional[str]:
        """Remove HTML tags from text."""
        if not text:
            return None
        import re
        clean = re.sub(r'<[^>]+>', '', text)
        return clean.strip()


@lru_cache
def get_media_search_service() -> MediaSearchService:
    """Get cached media search service instance."""
    return MediaSearchService()
