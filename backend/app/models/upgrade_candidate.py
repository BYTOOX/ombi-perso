"""
Upgrade candidate model for tracking VOSTFR content that can be upgraded to MULTI.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

if TYPE_CHECKING:
    from .monitored_series import MonitoredSeries


class UpgradeStatus(str, Enum):
    """Status of an upgrade candidate."""
    PENDING = "pending"            # Waiting for upgrade search
    SEARCHING = "searching"        # Currently searching for MULTI version
    FOUND = "found"                # MULTI version found, waiting for approval
    APPROVED = "approved"          # Approved for download
    DOWNLOADING = "downloading"    # Currently downloading
    PROCESSING = "processing"      # Processing (renaming, moving)
    COMPLETED = "completed"        # Upgrade completed successfully
    NO_UPGRADE = "no_upgrade"      # No MULTI version available
    FAILED = "failed"              # Upgrade failed
    SKIPPED = "skipped"            # Manually skipped by admin


class UpgradeCandidate(Base):
    """
    A media file that is a candidate for VOSTFR to MULTI upgrade.
    Tracks the current file and the upgrade process.
    """

    __tablename__ = "upgrade_candidates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Link to monitored series (optional - can be standalone)
    monitored_series_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("monitored_series.id"),
        nullable=True
    )

    # Current file information
    plex_rating_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    current_file_path: Mapped[str] = mapped_column(Text)
    current_audio_type: Mapped[str] = mapped_column(String(20))  # vostfr, vf
    current_quality: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    current_codec: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Media information
    title: Mapped[str] = mapped_column(String(500))
    tmdb_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    media_type: Mapped[str] = mapped_column(String(20), default="series")  # movie, series, anime

    # Episode info (for series)
    season: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    episode: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    episode_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Upgrade tracking
    status: Mapped[str] = mapped_column(
        String(20),
        default=UpgradeStatus.PENDING.value,
        index=True
    )
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Found upgrade info
    upgrade_torrent_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    upgrade_torrent_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    upgrade_torrent_size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    upgrade_torrent_seeders: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    upgrade_quality: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    upgrade_found_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Download tracking
    download_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("downloads.id"),
        nullable=True
    )
    download_progress: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0-100

    # Completion info
    new_file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    monitored_series: Mapped[Optional["MonitoredSeries"]] = relationship(
        "MonitoredSeries",
        back_populates="upgrade_candidates"
    )

    def __repr__(self):
        return f"<UpgradeCandidate {self.title} ({self.current_audio_type} -> MULTI) [{self.status}]>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "monitored_series_id": self.monitored_series_id,
            "plex_rating_key": self.plex_rating_key,
            "current_file_path": self.current_file_path,
            "current_audio_type": self.current_audio_type,
            "current_quality": self.current_quality,
            "title": self.title,
            "tmdb_id": self.tmdb_id,
            "year": self.year,
            "media_type": self.media_type,
            "season": self.season,
            "episode": self.episode,
            "episode_title": self.episode_title,
            "status": self.status,
            "status_message": self.status_message,
            "upgrade_torrent_name": self.upgrade_torrent_name,
            "upgrade_torrent_size": self.upgrade_torrent_size,
            "upgrade_torrent_seeders": self.upgrade_torrent_seeders,
            "upgrade_quality": self.upgrade_quality,
            "upgrade_found_at": self.upgrade_found_at.isoformat() if self.upgrade_found_at else None,
            "download_progress": self.download_progress,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
        }
