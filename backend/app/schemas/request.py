"""Request schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

from ..models.request import RequestStatus, MediaType


class RequestCreate(BaseModel):
    """Schema for creating a media request."""
    media_type: MediaType
    external_id: str  # TMDB or AniList ID
    source: str = "tmdb"  # tmdb or anilist
    
    title: str
    original_title: Optional[str] = None
    year: Optional[int] = None
    poster_url: Optional[str] = None
    overview: Optional[str] = None
    
    quality_preference: str = Field(default="1080p", pattern="^(720p|1080p|4K)$")
    seasons_requested: Optional[str] = None  # "1,2,3" or "all"


class RequestUpdate(BaseModel):
    """Schema for updating a request (admin only)."""
    status: Optional[RequestStatus] = None
    status_message: Optional[str] = None
    quality_preference: Optional[str] = None


class RequestResponse(BaseModel):
    """Schema for request response."""
    id: int
    user_id: int
    username: str
    
    media_type: MediaType
    external_id: str
    source: str
    
    title: str
    original_title: Optional[str] = None
    year: Optional[int] = None
    poster_url: Optional[str] = None
    overview: Optional[str] = None
    
    quality_preference: str
    seasons_requested: Optional[str] = None
    
    status: RequestStatus
    status_message: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    
    # Download info if available
    download_progress: Optional[float] = None
    download_speed: Optional[str] = None
    
    class Config:
        from_attributes = True


class RequestListResponse(BaseModel):
    """Schema for paginated request list."""
    items: List[RequestResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class UserRequestStats(BaseModel):
    """User's request statistics."""
    total_requests: int
    pending_requests: int
    completed_requests: int
    requests_today: int
    requests_remaining: int
