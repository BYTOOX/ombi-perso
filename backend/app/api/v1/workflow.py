"""
Workflow API endpoints for request pipeline tracking and human-in-the-loop actions.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...dependencies import get_async_db
from ...models.user import User
from ...models.request import MediaRequest
from ...models.workflow import RequestAction, ActionType, ActionStatus
from ...schemas.workflow import (
    WorkflowStepResponse, ActionResponse,
    WorkflowDetailResponse, ActionResolveRequest,
    RetryStepRequest, OpenActionsResponse
)
from ...services.workflow_service import WorkflowService
from .auth import get_current_user, get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflow", tags=["Workflow"])


# =========================================================================
# WORKFLOW DETAILS
# =========================================================================

@router.get("/requests/{request_id}", response_model=WorkflowDetailResponse)
async def get_request_workflow(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get workflow details for a request.
    Returns all steps and actions.
    Users can view their own requests, admins can view all.
    """
    # Get request with workflow data
    result = await db.execute(
        select(MediaRequest)
        .options(
            selectinload(MediaRequest.workflow_steps),
            selectinload(MediaRequest.actions)
        )
        .where(MediaRequest.id == request_id)
    )
    request = result.scalar_one_or_none()

    if not request:
        raise HTTPException(status_code=404, detail="Demande non trouvée")

    # Check access
    if not current_user.is_admin and request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Accès refusé")

    # Build response with enriched action data
    actions_response = []
    for action in request.actions:
        action_data = ActionResponse(
            id=action.id,
            request_id=action.request_id,
            request_title=request.title,
            workflow_step_id=action.workflow_step_id,
            action_type=action.action_type,
            status=action.status,
            priority=action.priority,
            payload_json=action.payload_json,
            resolution_json=action.resolution_json,
            message=action.message,
            created_at=action.created_at,
            resolved_at=action.resolved_at,
            resolved_by_id=action.resolved_by_id
        )
        actions_response.append(action_data)

    return WorkflowDetailResponse(
        request_id=request_id,
        request_title=request.title,
        request_status=request.status.value,
        steps=[
            WorkflowStepResponse.model_validate(step)
            for step in request.workflow_steps
        ],
        actions=actions_response
    )


# =========================================================================
# ACTION MANAGEMENT (Admin only)
# =========================================================================

@router.get("/actions", response_model=OpenActionsResponse)
async def list_actions(
    status: ActionStatus = Query(ActionStatus.OPEN),
    action_type: Optional[ActionType] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    List actions (admin only).
    Default: OPEN actions, sorted by priority then creation date.
    """
    query = (
        select(RequestAction)
        .options(selectinload(RequestAction.request))
        .where(RequestAction.status == status)
        .order_by(RequestAction.priority.desc(), RequestAction.created_at)
        .limit(limit)
    )

    if action_type:
        query = query.where(RequestAction.action_type == action_type)

    result = await db.execute(query)
    actions = result.scalars().all()

    # Build response with enriched data
    items = []
    for action in actions:
        action_data = ActionResponse(
            id=action.id,
            request_id=action.request_id,
            request_title=action.request.title if action.request else None,
            workflow_step_id=action.workflow_step_id,
            action_type=action.action_type,
            status=action.status,
            priority=action.priority,
            payload_json=action.payload_json,
            resolution_json=action.resolution_json,
            message=action.message,
            created_at=action.created_at,
            resolved_at=action.resolved_at,
            resolved_by_id=action.resolved_by_id
        )
        items.append(action_data)

    return OpenActionsResponse(items=items, total=len(items))


@router.get("/actions/{action_id}", response_model=ActionResponse)
async def get_action(
    action_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a single action by ID (admin only).
    """
    workflow_service = WorkflowService(db)
    action = await workflow_service.get_action_by_id(action_id)

    if not action:
        raise HTTPException(status_code=404, detail="Action non trouvée")

    return ActionResponse(
        id=action.id,
        request_id=action.request_id,
        request_title=action.request.title if action.request else None,
        workflow_step_id=action.workflow_step_id,
        action_type=action.action_type,
        status=action.status,
        priority=action.priority,
        payload_json=action.payload_json,
        resolution_json=action.resolution_json,
        message=action.message,
        created_at=action.created_at,
        resolved_at=action.resolved_at,
        resolved_by_id=action.resolved_by_id
    )


@router.post("/actions/{action_id}/resolve")
async def resolve_action(
    action_id: int,
    resolve_data: ActionResolveRequest,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Resolve an action with admin decision (admin only).
    The resolution data varies by action type.
    """
    workflow_service = WorkflowService(db)

    try:
        action = await workflow_service.resolve_action(
            action_id=action_id,
            user_id=current_user.id,
            resolution=resolve_data.resolution
        )

        # Handle follow-up based on action type
        if action.action_type == ActionType.FIX_SEARCH_QUERY:
            new_query = resolve_data.resolution.get("new_query")
            if new_query:
                # Re-queue search with new query
                from ...workers.request_worker import process_request_task
                process_request_task.delay(
                    action.request_id,
                    override_query=new_query
                )
                logger.info(f"Re-queued request {action.request_id} with new query: {new_query}")

        elif action.action_type == ActionType.CONFIRM_RENAME:
            # Future: handle rename confirmation
            pass

        elif action.action_type == ActionType.PICK_TORRENT:
            # Future: handle manual torrent selection
            pass

        return {
            "message": "Action résolue",
            "action_id": action_id,
            "status": action.status.value
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/actions/{action_id}/cancel")
async def cancel_action(
    action_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Cancel/dismiss an action (admin only).
    """
    workflow_service = WorkflowService(db)

    try:
        action = await workflow_service.cancel_action(action_id, current_user.id)
        return {
            "message": "Action annulée",
            "action_id": action_id,
            "status": action.status.value
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================================================================
# STEP RETRY (Admin only)
# =========================================================================

@router.post("/requests/{request_id}/retry-step")
async def retry_step(
    request_id: int,
    retry_data: RetryStepRequest,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retry a failed step (admin only).
    Resets the step and re-queues the request for processing.
    """
    # Verify request exists
    result = await db.execute(
        select(MediaRequest).where(MediaRequest.id == request_id)
    )
    request = result.scalar_one_or_none()

    if not request:
        raise HTTPException(status_code=404, detail="Demande non trouvée")

    workflow_service = WorkflowService(db)

    # Get the step
    step = await workflow_service.get_or_create_step(request_id, retry_data.step_key)

    # Check if step can be retried
    if step.attempts >= step.max_attempts:
        raise HTTPException(
            status_code=400,
            detail=f"L'étape a atteint le nombre maximum de tentatives ({step.max_attempts})"
        )

    # Reset step status
    await workflow_service.reset_step_for_retry(request_id, retry_data.step_key)

    # Cancel any open actions for this step
    result = await db.execute(
        select(RequestAction).where(
            RequestAction.workflow_step_id == step.id,
            RequestAction.status == ActionStatus.OPEN
        )
    )
    open_actions = result.scalars().all()
    for action in open_actions:
        await workflow_service.cancel_action(action.id, current_user.id)

    # Re-queue the request for processing
    from ...workers.request_worker import process_request_task
    process_request_task.delay(
        request_id,
        restart_from_step=retry_data.step_key.value
    )

    logger.info(f"Re-queued request {request_id} to retry step {retry_data.step_key.value}")

    return {
        "message": f"Étape {retry_data.step_key.value} relancée",
        "request_id": request_id,
        "attempt": step.attempts + 1
    }
