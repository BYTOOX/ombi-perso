"""Workflow schemas for request pipeline tracking and actions."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from ..models.workflow import (
    WorkflowStepKey, WorkflowStepStatus,
    ActionType, ActionStatus
)


class WorkflowStepResponse(BaseModel):
    """Response schema for a workflow step."""
    id: int
    request_id: int
    step_key: WorkflowStepKey
    step_order: int
    status: WorkflowStepStatus
    attempts: int
    max_attempts: int
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    last_error_code: Optional[str] = None
    last_error_message: Optional[str] = None
    artifacts_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate step duration."""
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None

    class Config:
        from_attributes = True


class ActionResponse(BaseModel):
    """Response schema for a human-in-the-loop action."""
    id: int
    request_id: int
    request_title: Optional[str] = None
    workflow_step_id: Optional[int] = None
    action_type: ActionType
    status: ActionStatus
    priority: int
    payload_json: Optional[Dict[str, Any]] = None
    resolution_json: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by_id: Optional[int] = None
    resolved_by_username: Optional[str] = None

    class Config:
        from_attributes = True


class WorkflowDetailResponse(BaseModel):
    """Full workflow detail for a request."""
    request_id: int
    request_title: str
    request_status: str
    steps: List[WorkflowStepResponse]
    actions: List[ActionResponse]


class ActionResolveRequest(BaseModel):
    """Request body for resolving an action."""
    resolution: Dict[str, Any]


class RetryStepRequest(BaseModel):
    """Request body for retrying a step."""
    step_key: WorkflowStepKey


class OpenActionsResponse(BaseModel):
    """Response for listing open actions."""
    items: List[ActionResponse]
    total: int
