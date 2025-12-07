"""
Rename settings model for storing file renaming configuration in database.
Supports Plex-compatible naming with TheTVDB as metadata source.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class RenameSettings(Base):
    """
    Configuration for file renaming stored in database.
    Allows admin panel configuration of naming formats and options.
    """
    
    __tablename__ = "rename_settings"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Language preferences
    preferred_language: Mapped[str] = mapped_column(
        String(20), 
        default="french",
        comment="Preferred language for audio: french, english, original"
    )
    title_language: Mapped[str] = mapped_column(
        String(20), 
        default="english",
        comment="Language for titles: french, english, romaji"
    )
    
    # Naming format templates
    movie_format: Mapped[str] = mapped_column(
        Text,
        default="{title} ({year})",
        comment="Template for movie naming"
    )
    series_format: Mapped[str] = mapped_column(
        Text,
        default="{title} ({year})/Season {season:02d}/{title} ({year}) - S{season:02d}E{episode:02d}",
        comment="Template for series naming"
    )
    anime_format: Mapped[str] = mapped_column(
        Text,
        default="{title} ({year})/Season {season:02d}/{title} ({year}) - S{season:02d}E{episode:02d}",
        comment="Template for anime naming"
    )
    
    # ID inclusion options
    include_tmdb_id: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Include {tmdb-xxx} in folder name"
    )
    include_tvdb_id: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Include {tvdb-xxx} in folder name"
    )
    
    # Character handling
    replace_special_chars: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Replace special characters (é→e, etc.)"
    )
    special_char_map: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="JSON mapping of special characters"
    )
    
    # Anime specific
    anime_title_preference: Mapped[str] = mapped_column(
        String(20),
        default="english",
        comment="Anime title preference: english, romaji, japanese"
    )
    
    # AI Fallback
    use_ai_fallback: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="Use AI when parsing fails"
    )
    
    # Metadata
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    
    def __repr__(self):
        return f"<RenameSettings id={self.id} lang={self.title_language}>"


class TitleMapping(Base):
    """
    Manual title mappings from torrent patterns to Plex titles.
    Used for handling edge cases that automatic resolution can't handle.
    """
    
    __tablename__ = "title_mappings"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Pattern to match (glob or regex)
    pattern: Mapped[str] = mapped_column(
        String(500),
        index=True,
        comment="Glob pattern to match torrent names"
    )
    
    # Target Plex title
    plex_title: Mapped[str] = mapped_column(
        String(500),
        comment="Correct Plex-compatible title"
    )
    
    # Media type this applies to
    media_type: Mapped[str] = mapped_column(
        String(20),
        comment="movie, series, anime"
    )
    
    # Optional external IDs for better matching
    tmdb_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    tvdb_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    
    # Year for disambiguation
    year: Mapped[Optional[int]] = mapped_column(nullable=True)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )
    
    def __repr__(self):
        return f"<TitleMapping '{self.pattern}' → '{self.plex_title}'>"
