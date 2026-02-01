"""
Workflow models for request pipeline tracking and human-in-the-loop actions.
"""
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional, Dict, Any

from sqlalchemy import (
    String, DateTime, Integer, ForeignKey, Text,
    Enum as SQLEnum, JSON, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

if TYPE_CHECKING:
    from .request import MediaRequest
    from .user import User


class WorkflowStepKey(str, Enum):
    """Pipeline step identifiers."""
    METADATA = "metadata"
    TORRENT_SEARCH = "torrent_search"
    TORRENT_PICK = "torrent_pick"
    DOWNLOAD_ADD = "download_add"
    DOWNLOAD_MONITOR = "download_monitor"
    POSTPROCESS = "postprocess"
    RENAME = "rename"
    MOVE = "move"
    PLEX_SCAN = "plex_scan"
    VERIFY = "verify"


class WorkflowStepStatus(str, Enum):
    """Step execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


class ActionType(str, Enum):
    """Types of human-in-the-loop actions."""
    FIX_SEARCH_QUERY = "fix_search_query"
    PICK_TORRENT = "pick_torrent"
    CONFIRM_RENAME = "confirm_rename"
    FIX_MAPPING = "fix_mapping"
    RETRY_STEP = "retry_step"
    MARK_UNAVAILABLE = "mark_unavailable"
    IGNORE = "ignore"


class ActionStatus(str, Enum):
    """Action resolution status."""
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class RequestWorkflowStep(Base):
    """
    Tracks individual pipeline steps for a media request.
    Stores execution state, timing, errors, and artifacts.
    """

    __tablename__ = "request_workflow_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("media_requests.id", ondelete="CASCADE"),
        index=True
    )

    # Step identification
    step_key: Mapped[WorkflowStepKey] = mapped_column(SQLEnum(WorkflowStepKey))
    step_order: Mapped[int] = mapped_column(Integer, default=0)

    # Execution state
    status: Mapped[WorkflowStepStatus] = mapped_column(
        SQLEnum(WorkflowStepStatus),
        default=WorkflowStepStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Error tracking
    last_error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Artifacts (JSON blob for step-specific data)
    artifacts_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    request: Mapped["MediaRequest"] = relationship(
        "MediaRequest", back_populates="workflow_steps"
    )

    # Indexes for common queries
    __table_args__ = (
        Index('ix_workflow_steps_request_status', 'request_id', 'status'),
        Index('ix_workflow_steps_step_key', 'step_key'),
    )

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate step duration."""
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None

    def __repr__(self):
        return f"<WorkflowStep {self.step_key.value} ({self.status.value})>"


class RequestAction(Base):
    """
    Human-in-the-loop action for admin intervention.
    Created when pipeline encounters issues requiring human decision.
    """

    __tablename__ = "request_actions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("media_requests.id", ondelete="CASCADE"),
        index=True
    )
    workflow_step_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("request_workflow_steps.id", ondelete="SET NULL"),
        nullable=True, index=True
    )

    # Action details
    action_type: Mapped[ActionType] = mapped_column(SQLEnum(ActionType))
    status: Mapped[ActionStatus] = mapped_column(
        SQLEnum(ActionStatus),
        default=ActionStatus.OPEN
    )
    priority: Mapped[int] = mapped_column(Integer, default=50)

    # Context/payload for the action
    payload_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Resolution data (filled when resolved)
    resolution_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Human-readable message
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    request: Mapped["MediaRequest"] = relationship(
        "MediaRequest", back_populates="actions"
    )
    workflow_step: Mapped[Optional["RequestWorkflowStep"]] = relationship(
        "RequestWorkflowStep"
    )
    resolved_by: Mapped[Optional["User"]] = relationship("User")

    # Indexes
    __table_args__ = (
        Index('ix_request_actions_status', 'status'),
        Index('ix_request_actions_type_status', 'action_type', 'status'),
    )

    def __repr__(self):
        return f"<RequestAction {self.action_type.value} ({self.status.value})>"
