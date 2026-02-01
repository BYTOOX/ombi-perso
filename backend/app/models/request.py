"""Media request model."""
from datetime import datetime
from enum import Enum
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Enum as SQLEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, TYPE_CHECKING, Dict, Any

from .database import Base

if TYPE_CHECKING:
    from .user import User
    from .download import Download
    from .workflow import RequestWorkflowStep, RequestAction


class MediaType(str, Enum):
    """Types of media."""
    MOVIE = "movie"
    ANIMATED_MOVIE = "animated_movie"
    SERIES = "series"
    ANIMATED_SERIES = "animated_series"
    ANIME = "anime"


class RequestStatus(str, Enum):
    """Request status workflow."""
    PENDING = "pending"          # Waiting to be processed
    SEARCHING = "searching"      # Searching for torrents
    AWAITING_APPROVAL = "awaiting_approval"  # Error detected, needs admin approval
    DOWNLOADING = "downloading"  # Download in progress
    PROCESSING = "processing"    # Renaming/moving files
    COMPLETED = "completed"      # Available on Plex
    ERROR = "error"             # Failed
    CANCELLED = "cancelled"      # Cancelled by user/admin


class MediaRequest(Base):
    """Media request from a user."""
    
    __tablename__ = "media_requests"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    
    # Media info
    media_type: Mapped[MediaType] = mapped_column(SQLEnum(MediaType))
    external_id: Mapped[str] = mapped_column(String(50), index=True)  # TMDB/AniList ID
    source: Mapped[str] = mapped_column(String(20), default="tmdb")   # tmdb, anilist
    
    # Display info
    title: Mapped[str] = mapped_column(String(500))
    original_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    poster_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Request details
    quality_preference: Mapped[str] = mapped_column(String(20), default="1080p")
    seasons_requested: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # e.g., "1,2,3" or "all"
    
    # Status
    status: Mapped[RequestStatus] = mapped_column(SQLEnum(RequestStatus), default=RequestStatus.PENDING)
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Celery task tracking
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # AI analysis result (stored as JSON)
    ai_analysis: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="requests")
    downloads: Mapped[list["Download"]] = relationship("Download", back_populates="request")
    workflow_steps: Mapped[list["RequestWorkflowStep"]] = relationship(
        "RequestWorkflowStep",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="RequestWorkflowStep.step_order"
    )
    actions: Mapped[list["RequestAction"]] = relationship(
        "RequestAction",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="RequestAction.created_at.desc()"
    )
    
    @property
    def is_anime(self) -> bool:
        """Check if this is an anime request."""
        return self.media_type == MediaType.ANIME
    
    @property
    def is_series(self) -> bool:
        """Check if this is a series-type request."""
        return self.media_type in (MediaType.SERIES, MediaType.ANIMATED_SERIES, MediaType.ANIME)
    
    def __repr__(self):
        return f"<MediaRequest {self.title} ({self.status.value})>"
