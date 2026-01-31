"""
Library analysis models for AI-powered library quality analysis.
Tracks analysis runs and individual issues found in the Plex library.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
import uuid

from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class AnalysisType(str, Enum):
    """Types of library analysis issues."""
    MISSING_COLLECTION = "missing_collection"   # Missing films in a collection/franchise
    LOW_QUALITY = "low_quality"                 # Low resolution (480p, SD)
    BAD_CODEC = "bad_codec"                     # Suboptimal codec (MPEG4, Xvid, non-HEVC)
    VOSTFR_UPGRADABLE = "vostfr_upgradable"     # VOSTFR content with MULTI available
    MISSING_EPISODES = "missing_episodes"       # Missing episodes in a series
    MISSING_SEASONS = "missing_seasons"         # Missing seasons in a series
    LOW_BITRATE = "low_bitrate"                 # Low bitrate audio/video
    BAD_AUDIO = "bad_audio"                     # Bad audio codec or quality
    DUPLICATE = "duplicate"                     # Duplicate media files


class Severity(str, Enum):
    """Issue severity levels."""
    LOW = "low"         # Minor issue, optional fix
    MEDIUM = "medium"   # Noticeable quality issue
    HIGH = "high"       # Significant quality problem


class AnalysisRunStatus(str, Enum):
    """Status of an analysis run."""
    PENDING = "pending"      # Queued, not started
    RUNNING = "running"      # Currently analyzing
    COMPLETED = "completed"  # Successfully completed
    FAILED = "failed"        # Failed with error
    CANCELLED = "cancelled"  # Cancelled by user


class AnalysisRun(Base):
    """
    Represents a single library analysis run.
    Groups multiple analysis results from one execution.
    """

    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Run information
    status: Mapped[str] = mapped_column(
        String(20),
        default=AnalysisRunStatus.PENDING.value,
        index=True
    )
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Analysis scope
    analysis_types: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)  # None = all types
    media_types: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)  # movie, series, anime

    # Progress tracking
    total_items_to_analyze: Mapped[int] = mapped_column(Integer, default=0)
    items_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    current_phase: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Results summary
    issues_found: Mapped[int] = mapped_column(Integer, default=0)
    issues_by_type: Mapped[Optional[Dict[str, int]]] = mapped_column(JSON, nullable=True)
    issues_by_severity: Mapped[Optional[Dict[str, int]]] = mapped_column(JSON, nullable=True)

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # User who triggered the analysis
    triggered_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )

    # Error information
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    results: Mapped[List["LibraryAnalysisResult"]] = relationship(
        "LibraryAnalysisResult",
        back_populates="analysis_run",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<AnalysisRun {self.id[:8]}... [{self.status}] {self.issues_found} issues>"

    @property
    def progress_percent(self) -> int:
        """Calculate progress percentage."""
        if self.total_items_to_analyze == 0:
            return 0
        return int((self.items_analyzed / self.total_items_to_analyze) * 100)

    @property
    def duration_seconds(self) -> Optional[int]:
        """Calculate run duration in seconds."""
        if not self.started_at:
            return None
        end = self.completed_at or datetime.utcnow()
        return int((end - self.started_at).total_seconds())

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "status": self.status,
            "status_message": self.status_message,
            "analysis_types": self.analysis_types,
            "media_types": self.media_types,
            "total_items_to_analyze": self.total_items_to_analyze,
            "items_analyzed": self.items_analyzed,
            "progress_percent": self.progress_percent,
            "current_phase": self.current_phase,
            "issues_found": self.issues_found,
            "issues_by_type": self.issues_by_type,
            "issues_by_severity": self.issues_by_severity,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LibraryAnalysisResult(Base):
    """
    Individual issue found during library analysis.
    Represents a specific problem with actionable recommendation.
    """

    __tablename__ = "library_analysis_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Link to analysis run
    analysis_run_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("analysis_runs.id"),
        index=True
    )

    # Issue classification
    analysis_type: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(20), default=Severity.MEDIUM.value)

    # Target media
    plex_rating_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tmdb_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    media_type: Mapped[str] = mapped_column(String(20))  # movie, series, anime
    poster_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Issue details
    issue_description: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(Text)

    # Specific issue data (depends on analysis_type)
    # For MISSING_COLLECTION:
    collection_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    collection_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    missing_titles: Mapped[Optional[List[Dict]]] = mapped_column(JSON, nullable=True)

    # For LOW_QUALITY / BAD_CODEC:
    current_quality: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    current_codec: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    current_bitrate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recommended_quality: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # For MISSING_EPISODES / MISSING_SEASONS:
    missing_seasons: Mapped[Optional[List[int]]] = mapped_column(JSON, nullable=True)
    missing_episodes: Mapped[Optional[Dict[int, List[int]]]] = mapped_column(JSON, nullable=True)  # {season: [episodes]}
    total_missing: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # For VOSTFR_UPGRADABLE:
    current_audio_languages: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    available_multi_torrent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # AI reasoning (for complex analysis)
    ai_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_confidence: Mapped[Optional[float]] = mapped_column(nullable=True)  # 0.0 to 1.0

    # User actions
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    dismissed_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dismiss_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_actioned: Mapped[bool] = mapped_column(Boolean, default=False)
    actioned_request_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("media_requests.id"),
        nullable=True
    )
    actioned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    analysis_run: Mapped["AnalysisRun"] = relationship(
        "AnalysisRun",
        back_populates="results"
    )

    def __repr__(self):
        return f"<LibraryAnalysisResult [{self.analysis_type}] {self.title} ({self.severity})>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "analysis_run_id": self.analysis_run_id,
            "analysis_type": self.analysis_type,
            "severity": self.severity,
            "plex_rating_key": self.plex_rating_key,
            "tmdb_id": self.tmdb_id,
            "title": self.title,
            "year": self.year,
            "media_type": self.media_type,
            "poster_url": self.poster_url,
            "issue_description": self.issue_description,
            "recommended_action": self.recommended_action,
            # Type-specific data
            "collection_name": self.collection_name,
            "missing_titles": self.missing_titles,
            "current_quality": self.current_quality,
            "current_codec": self.current_codec,
            "recommended_quality": self.recommended_quality,
            "missing_seasons": self.missing_seasons,
            "missing_episodes": self.missing_episodes,
            "total_missing": self.total_missing,
            "current_audio_languages": self.current_audio_languages,
            # AI info
            "ai_reasoning": self.ai_reasoning,
            "ai_confidence": self.ai_confidence,
            # Status
            "is_dismissed": self.is_dismissed,
            "dismissed_at": self.dismissed_at.isoformat() if self.dismissed_at else None,
            "is_actioned": self.is_actioned,
            "actioned_request_id": self.actioned_request_id,
            "actioned_at": self.actioned_at.isoformat() if self.actioned_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
