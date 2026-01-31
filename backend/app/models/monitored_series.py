"""
Monitored series model for tracking series for automatic downloads.
Supports both new episode monitoring (Sonarr-like) and VOSTFR to MULTI upgrades.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

if TYPE_CHECKING:
    from .upgrade_candidate import UpgradeCandidate
    from .episode_schedule import EpisodeReleaseSchedule


class MonitorType(str, Enum):
    """Type of monitoring for a series."""
    NEW_EPISODES = "new_episodes"      # Watch for new episode releases
    VOSTFR_UPGRADE = "vostfr_upgrade"  # Watch for MULTI versions of VOSTFR content
    BOTH = "both"                      # Both types of monitoring


class AudioPreference(str, Enum):
    """Audio preference for downloads."""
    MULTI = "multi"    # French + Original audio (preferred)
    VF = "vf"          # French audio only
    VOSTFR = "vostfr"  # Original audio with French subtitles
    ANY = "any"        # Any audio type


class QualityPreference(str, Enum):
    """Video quality preference."""
    UHD_4K = "4k"
    FHD_1080P = "1080p"
    HD_720P = "720p"
    ANY = "any"


class MonitoringStatus(str, Enum):
    """Monitoring status."""
    ACTIVE = "active"    # Actively monitoring
    PAUSED = "paused"    # Temporarily paused
    ENDED = "ended"      # Series has ended, no more new episodes


class MonitoredSeries(Base):
    """
    A series being monitored for automatic downloads.
    Tracks both new episode releases and VOSTFR upgrade opportunities.
    """

    __tablename__ = "monitored_series"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # External identifiers (at least one required)
    tmdb_id: Mapped[Optional[str]] = mapped_column(String(20), index=True, nullable=True)
    tvdb_id: Mapped[Optional[str]] = mapped_column(String(20), index=True, nullable=True)
    anilist_id: Mapped[Optional[str]] = mapped_column(String(20), index=True, nullable=True)
    imdb_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Media information
    title: Mapped[str] = mapped_column(String(500))
    original_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    media_type: Mapped[str] = mapped_column(String(20), default="series")  # series, anime
    poster_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    backdrop_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Monitoring settings
    monitor_type: Mapped[str] = mapped_column(
        String(20),
        default=MonitorType.NEW_EPISODES.value
    )
    quality_preference: Mapped[str] = mapped_column(
        String(20),
        default=QualityPreference.FHD_1080P.value
    )
    audio_preference: Mapped[str] = mapped_column(
        String(20),
        default=AudioPreference.MULTI.value
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        default=MonitoringStatus.ACTIVE.value
    )

    # Episode tracking (for new episode monitoring)
    total_seasons: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_season: Mapped[int] = mapped_column(Integer, default=1)
    current_episode: Mapped[int] = mapped_column(Integer, default=0)

    # Release schedule tracking
    next_air_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_air_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    air_day_of_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0=Monday, 6=Sunday

    # Check timestamps
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_download_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # User who added the series
    added_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    upgrade_candidates: Mapped[List["UpgradeCandidate"]] = relationship(
        "UpgradeCandidate",
        back_populates="monitored_series",
        cascade="all, delete-orphan"
    )
    episode_schedules: Mapped[List["EpisodeReleaseSchedule"]] = relationship(
        "EpisodeReleaseSchedule",
        back_populates="monitored_series",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<MonitoredSeries {self.title} ({self.status})>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "tmdb_id": self.tmdb_id,
            "tvdb_id": self.tvdb_id,
            "anilist_id": self.anilist_id,
            "title": self.title,
            "original_title": self.original_title,
            "year": self.year,
            "media_type": self.media_type,
            "poster_url": self.poster_url,
            "monitor_type": self.monitor_type,
            "quality_preference": self.quality_preference,
            "audio_preference": self.audio_preference,
            "status": self.status,
            "total_seasons": self.total_seasons,
            "current_season": self.current_season,
            "current_episode": self.current_episode,
            "next_air_date": self.next_air_date.isoformat() if self.next_air_date else None,
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
