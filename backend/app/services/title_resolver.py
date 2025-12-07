"""
Title resolver service for resolving media titles via TMDB and TheTVDB.
Used for Plex-compatible naming.
"""
import logging
import re
from typing import Optional, Dict, Any, List, Tuple
import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)


class TitleResolverService:
    """
    Service for resolving media titles using external APIs.
    Supports TMDB and TheTVDB for maximum Plex compatibility.
    """
    
    TMDB_BASE_URL = "https://api.themoviedb.org/3"
    
    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    async def client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    # =========================================================================
    # TITLE RESOLUTION
    # =========================================================================
    
    async def resolve_title(
        self,
        query: str,
        media_type: str,
        year: Optional[int] = None,
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Resolve a media title to Plex-compatible format.
        
        Args:
            query: Search query or torrent name
            media_type: movie, series, anime
            year: Optional year for disambiguation
            tmdb_id: Optional TMDB ID if known
            tvdb_id: Optional TVDB ID if known
            
        Returns:
            Dict with resolved title info
        """
        # Clean the query from torrent garbage
        clean_query = self._clean_torrent_name(query)
        
        if media_type == "movie":
            return await self._resolve_movie(clean_query, year, tmdb_id)
        else:
            return await self._resolve_series(clean_query, year, tmdb_id, tvdb_id, is_anime=(media_type == "anime"))
    
    async def _resolve_movie(
        self,
        query: str,
        year: Optional[int] = None,
        tmdb_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Resolve a movie title via TMDB."""
        
        # If we have TMDB ID, fetch directly
        if tmdb_id:
            movie = await self._fetch_tmdb_movie(tmdb_id)
            if movie:
                return movie
        
        # Search TMDB
        results = await self._search_tmdb("movie", query, year)
        
        if not results:
            return self._fallback_result(query, year, "movie")
        
        # Take best match
        movie = results[0]
        return {
            "title": movie.get("title", query),
            "original_title": movie.get("original_title"),
            "year": self._extract_year(movie.get("release_date")),
            "tmdb_id": movie.get("id"),
            "tvdb_id": None,
            "media_type": "movie",
            "confidence": 0.9 if year and str(year) in movie.get("release_date", "") else 0.7,
            "source": "tmdb"
        }
    
    async def _resolve_series(
        self,
        query: str,
        year: Optional[int] = None,
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None,
        is_anime: bool = False
    ) -> Dict[str, Any]:
        """Resolve a TV series/anime title via TMDB (which has TVDB mapping)."""
        
        # If we have TMDB ID, fetch directly
        if tmdb_id:
            series = await self._fetch_tmdb_series(tmdb_id)
            if series:
                return series
        
        # Search TMDB for TV
        results = await self._search_tmdb("tv", query, year)
        
        if not results:
            return self._fallback_result(query, year, "anime" if is_anime else "series")
        
        # Take best match
        series = results[0]
        
        # Fetch full details to get external IDs
        details = await self._fetch_tmdb_series(series.get("id"))
        
        if details:
            return details
        
        return {
            "title": series.get("name", query),
            "original_title": series.get("original_name"),
            "year": self._extract_year(series.get("first_air_date")),
            "tmdb_id": series.get("id"),
            "tvdb_id": None,
            "media_type": "anime" if is_anime else "series",
            "confidence": 0.8,
            "source": "tmdb"
        }
    
    async def _fetch_tmdb_movie(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """Fetch movie details from TMDB."""
        try:
            client = await self.client
            response = await client.get(
                f"{self.TMDB_BASE_URL}/movie/{tmdb_id}",
                params={"api_key": self.settings.tmdb_api_key, "language": "fr-FR"}
            )
            
            if response.status_code != 200:
                return None
            
            movie = response.json()
            
            return {
                "title": movie.get("title"),
                "original_title": movie.get("original_title"),
                "year": self._extract_year(movie.get("release_date")),
                "tmdb_id": movie.get("id"),
                "tvdb_id": None,
                "media_type": "movie",
                "confidence": 1.0,
                "source": "tmdb"
            }
        except Exception as e:
            logger.error(f"TMDB movie fetch error: {e}")
            return None
    
    async def _fetch_tmdb_series(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """Fetch TV series details from TMDB with external IDs."""
        try:
            client = await self.client
            
            # Fetch details
            response = await client.get(
                f"{self.TMDB_BASE_URL}/tv/{tmdb_id}",
                params={"api_key": self.settings.tmdb_api_key, "language": "fr-FR"}
            )
            
            if response.status_code != 200:
                return None
            
            series = response.json()
            
            # Fetch external IDs (includes TVDB)
            ext_response = await client.get(
                f"{self.TMDB_BASE_URL}/tv/{tmdb_id}/external_ids",
                params={"api_key": self.settings.tmdb_api_key}
            )
            
            tvdb_id = None
            if ext_response.status_code == 200:
                ext_ids = ext_response.json()
                tvdb_id = ext_ids.get("tvdb_id")
            
            # Detect if anime (Japanese origin with animation genre)
            is_anime = (
                series.get("origin_country") == ["JP"] and
                16 in [g.get("id") for g in series.get("genres", [])]  # Animation genre
            )
            
            return {
                "title": series.get("name"),
                "original_title": series.get("original_name"),
                "year": self._extract_year(series.get("first_air_date")),
                "tmdb_id": series.get("id"),
                "tvdb_id": tvdb_id,
                "media_type": "anime" if is_anime else "series",
                "confidence": 1.0,
                "source": "tmdb",
                "seasons": series.get("number_of_seasons", 1),
                "episodes": series.get("number_of_episodes", 0)
            }
        except Exception as e:
            logger.error(f"TMDB series fetch error: {e}")
            return None
    
    async def _search_tmdb(
        self,
        media_type: str,  # "movie" or "tv"
        query: str,
        year: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Search TMDB for media."""
        try:
            client = await self.client
            
            params = {
                "api_key": self.settings.tmdb_api_key,
                "query": query,
                "language": "fr-FR"
            }
            
            if year:
                params["year" if media_type == "movie" else "first_air_date_year"] = year
            
            response = await client.get(
                f"{self.TMDB_BASE_URL}/search/{media_type}",
                params=params
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            return data.get("results", [])[:5]  # Top 5 results
            
        except Exception as e:
            logger.error(f"TMDB search error: {e}")
            return []
    
    # =========================================================================
    # SEASON/EPISODE PARSING
    # =========================================================================
    
    def extract_season_episode(self, filename: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Extract season and episode numbers from a filename.
        
        Supports formats:
        - S01E01, S1E1
        - 1x01
        - [01] (anime absolute)
        - Episode 1
        - - 01 -
        """
        patterns = [
            r'[Ss](\d{1,2})[Ee](\d{1,3})',       # S01E01
            r'[Ss](\d{1,2})\.?[Ee](\d{1,3})',    # S01.E01
            r'(\d{1,2})[xX](\d{1,3})',            # 1x01
            r'Season\s*(\d{1,2}).*Episode\s*(\d{1,3})',  # Season 1 Episode 1
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return (int(match.group(1)), int(match.group(2)))
        
        # Try anime absolute number (usually season 1)
        episode = self._extract_anime_episode(filename)
        if episode:
            return (1, episode)
        
        return (None, None)
    
    def _extract_anime_episode(self, filename: str) -> Optional[int]:
        """Extract episode number from anime-style filename."""
        patterns = [
            r'[\[\s-](\d{2,4})[\]\s-](?!p)',  # [01] or - 01 - (not 1080p)
            r'Episode\s*(\d{1,4})',
            r'Ep\.?\s*(\d{1,4})',
            r'\s-\s(\d{2,4})\s',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                ep = int(match.group(1))
                # Sanity check - episode numbers shouldn't be resolution
                if ep < 10000 and ep not in [480, 720, 1080, 2160, 4320]:
                    return ep
        
        return None
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def _clean_torrent_name(self, name: str) -> str:
        """
        Clean torrent name to extract the actual title.
        Removes release groups, quality tags, etc.
        """
        # Remove file extension
        name = re.sub(r'\.(mkv|mp4|avi|mov|wmv|flv|webm|m4v)$', '', name, flags=re.IGNORECASE)
        
        # Remove release group brackets [SubsPlease], (Group), etc.
        name = re.sub(r'\[.*?\]', '', name)
        name = re.sub(r'\(.*?\)', '', name)
        
        # Remove quality tags
        quality_tags = [
            r'1080p', r'720p', r'480p', r'2160p', r'4K', r'UHD',
            r'BluRay', r'BDRip', r'WEB-?DL', r'HDTV', r'DVDRip',
            r'x264', r'x265', r'HEVC', r'H\.?264', r'H\.?265',
            r'10bit', r'HDR', r'REMUX',
            r'VOSTFR', r'FRENCH', r'MULTI', r'VF', r'VO',
            r'AAC', r'AC3', r'DTS', r'FLAC', r'TrueHD', r'Atmos',
        ]
        for tag in quality_tags:
            name = re.sub(rf'\b{tag}\b', '', name, flags=re.IGNORECASE)
        
        # Remove episode info for series
        name = re.sub(r'[Ss]\d{1,2}[Ee]\d{1,3}.*', '', name)
        name = re.sub(r'\s*-\s*\d{2,4}\s*', ' ', name)
        
        # Clean up spaces and dots
        name = name.replace('.', ' ')
        name = name.replace('_', ' ')
        name = re.sub(r'\s+', ' ', name)
        name = name.strip(' -')
        
        return name
    
    def _extract_year(self, date_str: Optional[str]) -> Optional[int]:
        """Extract year from a date string."""
        if not date_str:
            return None
        match = re.search(r'(\d{4})', date_str)
        return int(match.group(1)) if match else None
    
    def _fallback_result(
        self,
        query: str,
        year: Optional[int],
        media_type: str
    ) -> Dict[str, Any]:
        """Return a fallback result when resolution fails."""
        return {
            "title": query,
            "original_title": query,
            "year": year,
            "tmdb_id": None,
            "tvdb_id": None,
            "media_type": media_type,
            "confidence": 0.3,
            "source": "fallback"
        }


# Singleton instance
_title_resolver_service: Optional[TitleResolverService] = None


def get_title_resolver_service() -> TitleResolverService:
    """Get title resolver service instance."""
    global _title_resolver_service
    if _title_resolver_service is None:
        _title_resolver_service = TitleResolverService()
    return _title_resolver_service
