"""Download schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

from ..models.download import DownloadStatus


class DownloadResponse(BaseModel):
    """Schema for download response."""
    id: int
    request_id: int
    
    torrent_name: str
    torrent_hash: str
    source_site: str
    
    size_bytes: int
    size_gb: float
    seeders: int
    leechers: int
    
    status: DownloadStatus
    progress: float
    download_speed: int
    upload_speed: int
    
    ai_score: Optional[float] = None
    ai_reasoning: Optional[str] = None
    
    download_path: Optional[str] = None
    final_path: Optional[str] = None
    
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    seed_until: Optional[datetime] = None
    
    error_message: Optional[str] = None
    
    class Config:
        from_attributes = True


class DownloadStats(BaseModel):
    """Global download statistics."""
    active_downloads: int
    seeding_count: int
    queued_count: int
    completed_today: int
    
    total_download_speed: int  # bytes/s
    total_upload_speed: int    # bytes/s
    
    disk_usage_gb: float
    disk_limit_gb: float
    disk_usage_percent: float


class DownloadListResponse(BaseModel):
    """Paginated download list."""
    items: List[DownloadResponse]
    total: int
    stats: DownloadStats
