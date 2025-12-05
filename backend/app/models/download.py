"""Download tracking model."""
from datetime import datetime
from enum import Enum
from sqlalchemy import String, DateTime, Integer, Float, ForeignKey, Text, Enum as SQLEnum, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, TYPE_CHECKING

from .database import Base

if TYPE_CHECKING:
    from .request import MediaRequest


class DownloadStatus(str, Enum):
    """Download status."""
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    SEEDING = "seeding"
    PROCESSING = "processing"  # Moving/renaming
    COMPLETED = "completed"
    ERROR = "error"


class Download(Base):
    """Active/completed download tracking."""
    
    __tablename__ = "downloads"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("media_requests.id"), index=True)
    
    # Torrent info
    torrent_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    torrent_name: Mapped[str] = mapped_column(String(500))
    magnet_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    torrent_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Source info
    source_site: Mapped[str] = mapped_column(String(50), default="ygg")
    seeders: Mapped[int] = mapped_column(Integer, default=0)
    leechers: Mapped[int] = mapped_column(Integer, default=0)
    
    # Size
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    
    # Progress
    status: Mapped[DownloadStatus] = mapped_column(SQLEnum(DownloadStatus), default=DownloadStatus.QUEUED)
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0-100
    download_speed: Mapped[int] = mapped_column(BigInteger, default=0)  # bytes/s
    upload_speed: Mapped[int] = mapped_column(BigInteger, default=0)   # bytes/s
    
    # File location
    download_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    final_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    # AI scoring
    ai_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    seed_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    request: Mapped["MediaRequest"] = relationship("MediaRequest", back_populates="downloads")
    
    @property
    def size_gb(self) -> float:
        """Get size in gigabytes."""
        return self.size_bytes / (1024 ** 3)
    
    @property
    def is_complete(self) -> bool:
        """Check if download is complete."""
        return self.status in (DownloadStatus.COMPLETED, DownloadStatus.SEEDING)
    
    def __repr__(self):
        return f"<Download {self.torrent_name[:50]} ({self.progress:.1f}%)>"
