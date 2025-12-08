"""Media schemas for search and details."""
from datetime import date
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class MediaType(str, Enum):
    """Media type for search."""
    ALL = "all"
    MOVIE = "movie"
    TV = "tv"  # Alias for series (used by frontend)
    SERIES = "series"
    ANIME = "anime"


class MediaSource(str, Enum):
    """Data source."""
    TMDB = "tmdb"
    ANILIST = "anilist"


class MediaSearchResult(BaseModel):
    """Schema for search results."""
    id: str  # External ID (TMDB or AniList)
    source: MediaSource
    media_type: str  # movie, series, anime, etc.
    
    title: str
    original_title: Optional[str] = None
    year: Optional[int] = None
    
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None
    
    overview: Optional[str] = None
    rating: Optional[float] = None
    vote_count: Optional[int] = None
    
    # For series
    first_air_date: Optional[date] = None
    seasons_count: Optional[int] = None
    episodes_count: Optional[int] = None
    status: Optional[str] = None  # Ongoing, Completed, etc.
    
    # For anime
    romaji_title: Optional[str] = None
    native_title: Optional[str] = None
    genres: List[str] = Field(default_factory=list)
    studios: List[str] = Field(default_factory=list)
    
    # Availability check
    already_available: bool = False
    plex_rating_key: Optional[str] = None
    available_quality: Optional[str] = None  # e.g., "1080p", "4K"
    available_seasons: List[int] = Field(default_factory=list)  # For series


class MediaDetails(MediaSearchResult):
    """Extended media details."""
    # Cast & crew
    cast: List[dict] = Field(default_factory=list)
    crew: List[dict] = Field(default_factory=list)
    
    # Anime specific
    mal_id: Optional[int] = None
    anilist_id: Optional[int] = None
    
    # Recommendations
    similar: List["MediaSearchResult"] = Field(default_factory=list)
    recommendations: List["MediaSearchResult"] = Field(default_factory=list)
    
    # Trailers
    trailer_url: Optional[str] = None


class TorrentResult(BaseModel):
    """Schema for torrent search results."""
    id: str
    name: str
    size_bytes: int
    size_human: str
    seeders: int
    leechers: int
    upload_date: Optional[date] = None
    uploader: Optional[str] = None
    category: Optional[str] = None
    
    # Download info
    torrent_url: Optional[str] = None
    magnet_link: Optional[str] = None
    
    # AI analysis
    ai_score: Optional[float] = None
    ai_reasoning: Optional[str] = None
    quality: Optional[str] = None  # 720p, 1080p, 4K, etc.
    release_group: Optional[str] = None
    has_french_audio: bool = False
    has_french_subs: bool = False
