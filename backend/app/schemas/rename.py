"""
Pydantic schemas for file renaming configuration.
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class RenameSettingsBase(BaseModel):
    """Base schema for rename settings."""
    preferred_language: str = Field(
        default="french",
        description="Preferred audio language: french, english, original"
    )
    title_language: str = Field(
        default="english",
        description="Language for titles: french, english, romaji"
    )
    
    # Naming templates
    movie_format: str = Field(
        default="{title} ({year})",
        description="Template for movie file/folder naming"
    )
    series_format: str = Field(
        default="{title} ({year})/Season {season:02d}/{title} ({year}) - S{season:02d}E{episode:02d}",
        description="Template for series file/folder naming"
    )
    anime_format: str = Field(
        default="{title} ({year})/Season {season:02d}/{title} ({year}) - S{season:02d}E{episode:02d}",
        description="Template for anime file/folder naming"
    )
    
    # ID options
    include_tmdb_id: bool = Field(
        default=False,
        description="Include TMDB ID in folder name"
    )
    include_tvdb_id: bool = Field(
        default=False,
        description="Include TVDB ID in folder name"
    )
    
    # Character handling
    replace_special_chars: bool = Field(
        default=False,
        description="Replace special characters (é→e)"
    )
    special_char_map: Optional[str] = Field(
        default=None,
        description="JSON mapping of special characters"
    )
    
    # Anime specific
    anime_title_preference: str = Field(
        default="english",
        description="Anime title preference: english, romaji, japanese"
    )
    
    # AI
    use_ai_fallback: bool = Field(
        default=True,
        description="Use AI when automatic parsing fails"
    )


class RenameSettingsUpdate(RenameSettingsBase):
    """Schema for updating rename settings."""
    pass


class RenameSettingsResponse(RenameSettingsBase):
    """Schema for rename settings response."""
    id: int
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Title Mapping schemas
class TitleMappingBase(BaseModel):
    """Base schema for title mappings."""
    pattern: str = Field(
        ...,
        description="Glob pattern to match torrent names",
        min_length=2,
        max_length=500
    )
    plex_title: str = Field(
        ...,
        description="Correct Plex-compatible title",
        min_length=1,
        max_length=500
    )
    media_type: str = Field(
        ...,
        description="Media type: movie, series, anime"
    )
    tmdb_id: Optional[int] = Field(
        default=None,
        description="TMDB ID for better matching"
    )
    tvdb_id: Optional[int] = Field(
        default=None,
        description="TVDB ID for better matching"
    )
    year: Optional[int] = Field(
        default=None,
        description="Year for disambiguation"
    )


class TitleMappingCreate(TitleMappingBase):
    """Schema for creating a title mapping."""
    pass


class TitleMappingResponse(TitleMappingBase):
    """Schema for title mapping response."""
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# Rename preview schemas
class RenamePreviewRequest(BaseModel):
    """Schema for rename preview request."""
    filename: str = Field(
        ...,
        description="Original filename to preview",
        min_length=1
    )
    media_type: str = Field(
        ...,
        description="Media type: movie, series, anime"
    )
    tmdb_id: Optional[int] = Field(
        default=None,
        description="TMDB ID if known"
    )
    tvdb_id: Optional[int] = Field(
        default=None,
        description="TVDB ID if known"
    )
    title_override: Optional[str] = Field(
        default=None,
        description="Override the resolved title"
    )


class RenamePreviewResponse(BaseModel):
    """Schema for rename preview response."""
    original: str = Field(..., description="Original filename")
    renamed: str = Field(..., description="Renamed filename")
    folder_structure: str = Field(..., description="Full folder path")
    sources_used: List[str] = Field(
        default_factory=list,
        description="Metadata sources used"
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence score 0-1"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Any warnings during resolution"
    )
    resolved_info: Optional[dict] = Field(
        default=None,
        description="Resolved metadata info"
    )


class RenameTestRequest(BaseModel):
    """Schema for testing rename on a sample filename."""
    filename: str = Field(
        ...,
        description="Sample filename to test",
        examples=["[SubsPlease] One Piece - 1089 (1080p).mkv"]
    )
    media_type: str = Field(
        default="anime",
        description="Media type: movie, series, anime"
    )
