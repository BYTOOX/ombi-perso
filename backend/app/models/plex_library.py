"""
Plex Library Cache model for fast availability checks.
Stores a local cache of Plex library items with their external IDs (TMDB/TVDB/IMDB).
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, DateTime, Integer, Float, Text, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class PlexLibraryItem(Base):
    """
    Cache of Plex library items for fast availability checks.
    
    Stores media items from Plex with their external identifiers (TMDB, TVDB, IMDB)
    to enable quick matching against search results without querying Plex directly.
    """
    
    __tablename__ = "plex_library_cache"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Plex identifiers
    plex_rating_key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    plex_library_title: Mapped[str] = mapped_column(String(200))  # e.g., "Films", "Séries TV"
    
    # External IDs for matching (indexed for fast lookups)
    tmdb_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    tvdb_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    imdb_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    
    # Media info
    title: Mapped[str] = mapped_column(String(500))
    original_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    media_type: Mapped[str] = mapped_column(String(20))  # movie, show
    
    # Quality info (stored as JSON for flexibility)
    # Example: {"resolution": "1080p", "video_codec": "HEVC", "bit_depth": "10bit", "hdr": true}
    quality_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Audio languages available (e.g., ["fra", "eng", "jpn"])
    audio_languages: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    
    # Subtitle languages available (e.g., ["fra", "eng"])
    subtitle_languages: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    
    # File size in GB
    file_size_gb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # For series: list of available season numbers (e.g., [1, 2, 3])
    seasons_available: Mapped[Optional[List[int]]] = mapped_column(JSON, nullable=True)
    
    # For series: total number of episodes available
    total_episodes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Poster URL from Plex (for verification in admin panel)
    poster_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Timestamps
    plex_added_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Composite indexes for common queries
    __table_args__ = (
        # Index for batch availability checks by TMDB ID + type
        Index('ix_plex_cache_tmdb_type', 'tmdb_id', 'media_type'),
        # Index for batch availability checks by TVDB ID + type
        Index('ix_plex_cache_tvdb_type', 'tvdb_id', 'media_type'),
    )
    
    def __repr__(self):
        return f"<PlexLibraryItem {self.title} ({self.year}) - {self.media_type}>"
    
    @property
    def has_external_id(self) -> bool:
        """Check if item has at least one external ID for matching."""
        return bool(self.tmdb_id or self.tvdb_id or self.imdb_id)
    
    @property
    def is_series(self) -> bool:
        """Check if this is a series-type item."""
        return self.media_type == "show"
    
    def to_availability_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary for availability response."""
        return {
            "available": True,
            "plex_rating_key": self.plex_rating_key,
            "title": self.title,
            "year": self.year,
            "quality_info": self.quality_info or {},
            "audio_languages": self.audio_languages or [],
            "subtitle_languages": self.subtitle_languages or [],
            "file_size_gb": self.file_size_gb,
            "seasons_available": self.seasons_available or [],
            "total_episodes": self.total_episodes,
        }


class PlexSyncStatus(Base):
    """
    Tracks the status of Plex library synchronization.
    Single row table to store sync metadata.
    """
    
    __tablename__ = "plex_sync_status"
    
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    
    # Last successful sync timestamp
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Number of items synced in last sync
    last_sync_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Total items currently in cache
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    
    # Items without external IDs (needs admin attention)
    items_without_guid: Mapped[int] = mapped_column(Integer, default=0)
    
    # Last sync status message
    last_sync_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Is sync currently in progress?
    sync_in_progress: Mapped[bool] = mapped_column(default=False)
    
    def __repr__(self):
        return f"<PlexSyncStatus last_sync={self.last_sync_at} items={self.total_items}>"
