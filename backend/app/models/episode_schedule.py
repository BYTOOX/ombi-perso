"""
Episode release schedule model for tracking upcoming and aired episodes.
Used for automatic episode download scheduling.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

if TYPE_CHECKING:
    from .monitored_series import MonitoredSeries


class EpisodeStatus(str, Enum):
    """Status of a scheduled episode."""
    UPCOMING = "upcoming"                # Not yet aired
    AIRED = "aired"                      # Aired, waiting for torrent search
    SEARCHING = "searching"              # Searching for torrent
    FOUND = "found"                      # Torrent found, waiting for approval
    PENDING_APPROVAL = "pending_approval"  # Waiting for admin approval
    APPROVED = "approved"                # Approved, ready for download
    DOWNLOADING = "downloading"          # Currently downloading
    PROCESSING = "processing"            # Processing (renaming, moving)
    COMPLETED = "completed"              # Successfully downloaded and processed
    NOT_FOUND = "not_found"              # Torrent not found (will retry)
    FAILED = "failed"                    # Download/processing failed
    SKIPPED = "skipped"                  # Manually skipped


class EpisodeReleaseSchedule(Base):
    """
    Tracks episode release dates and download status.
    Used to monitor when episodes air and trigger automatic downloads.
    """

    __tablename__ = "episode_release_schedules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Link to monitored series
    monitored_series_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("monitored_series.id"),
        index=True
    )

    # Episode identification
    season: Mapped[int] = mapped_column(Integer)
    episode: Mapped[int] = mapped_column(Integer)
    episode_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    episode_overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # External IDs
    tmdb_episode_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    tvdb_episode_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Air date information
    air_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    air_date_source: Mapped[str] = mapped_column(String(20), default="tmdb")  # tmdb, tvdb, anilist

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20),
        default=EpisodeStatus.UPCOMING.value,
        index=True
    )
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Torrent information (when found)
    found_torrent_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    found_torrent_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    found_torrent_size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    found_torrent_seeders: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    found_torrent_quality: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    found_torrent_audio: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    torrent_found_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Download tracking
    download_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("downloads.id"),
        nullable=True
    )
    media_request_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("media_requests.id"),
        nullable=True
    )

    # Search tracking
    search_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_search_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_search_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Approval tracking
    approved_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Completion tracking
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    final_file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    monitored_series: Mapped["MonitoredSeries"] = relationship(
        "MonitoredSeries",
        back_populates="episode_schedules"
    )

    def __repr__(self):
        return f"<EpisodeReleaseSchedule S{self.season:02d}E{self.episode:02d} [{self.status}]>"

    @property
    def episode_code(self) -> str:
        """Return episode code like S01E05."""
        return f"S{self.season:02d}E{self.episode:02d}"

    @property
    def is_aired(self) -> bool:
        """Check if episode has aired."""
        return datetime.utcnow() >= self.air_date

    @property
    def can_search(self) -> bool:
        """Check if we can search for this episode."""
        return (
            self.is_aired and
            self.status in [
                EpisodeStatus.AIRED.value,
                EpisodeStatus.NOT_FOUND.value
            ]
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "monitored_series_id": self.monitored_series_id,
            "season": self.season,
            "episode": self.episode,
            "episode_code": self.episode_code,
            "episode_title": self.episode_title,
            "air_date": self.air_date.isoformat() if self.air_date else None,
            "air_date_source": self.air_date_source,
            "status": self.status,
            "status_message": self.status_message,
            "is_aired": self.is_aired,
            "found_torrent_name": self.found_torrent_name,
            "found_torrent_size": self.found_torrent_size,
            "found_torrent_seeders": self.found_torrent_seeders,
            "found_torrent_quality": self.found_torrent_quality,
            "found_torrent_audio": self.found_torrent_audio,
            "torrent_found_at": self.torrent_found_at.isoformat() if self.torrent_found_at else None,
            "search_attempts": self.search_attempts,
            "last_search_at": self.last_search_at.isoformat() if self.last_search_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
