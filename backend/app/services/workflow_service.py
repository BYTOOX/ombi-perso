"""
Workflow Service - Manages workflow steps and human-in-the-loop actions.

Provides idempotent operations for pipeline instrumentation.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.workflow import (
    RequestWorkflowStep, RequestAction,
    WorkflowStepKey, WorkflowStepStatus,
    ActionType, ActionStatus
)

logger = logging.getLogger(__name__)


class WorkflowService:
    """
    Service for managing workflow steps and actions.
    Provides idempotent operations for pipeline instrumentation.
    """

    # Define step order for consistent pipeline execution
    STEP_ORDER = {
        WorkflowStepKey.METADATA: 1,
        WorkflowStepKey.TORRENT_SEARCH: 2,
        WorkflowStepKey.TORRENT_PICK: 3,
        WorkflowStepKey.DOWNLOAD_ADD: 4,
        WorkflowStepKey.DOWNLOAD_MONITOR: 5,
        WorkflowStepKey.POSTPROCESS: 6,
        WorkflowStepKey.RENAME: 7,
        WorkflowStepKey.MOVE: 8,
        WorkflowStepKey.PLEX_SCAN: 9,
        WorkflowStepKey.VERIFY: 10,
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # WORKFLOW STEP MANAGEMENT
    # =========================================================================

    async def get_or_create_step(
        self,
        request_id: int,
        step_key: WorkflowStepKey
    ) -> RequestWorkflowStep:
        """
        Get existing step or create new one (idempotent).
        """
        result = await self.db.execute(
            select(RequestWorkflowStep).where(
                and_(
                    RequestWorkflowStep.request_id == request_id,
                    RequestWorkflowStep.step_key == step_key
                )
            )
        )
        step = result.scalar_one_or_none()

        if not step:
            step = RequestWorkflowStep(
                request_id=request_id,
                step_key=step_key,
                step_order=self.STEP_ORDER.get(step_key, 99),
                status=WorkflowStepStatus.PENDING
            )
            self.db.add(step)
            await self.db.flush()
            logger.info(f"Created workflow step {step_key.value} for request {request_id}")

        return step

    async def start_step(
        self,
        request_id: int,
        step_key: WorkflowStepKey
    ) -> RequestWorkflowStep:
        """
        Mark step as running. Idempotent - won't restart if already running.
        """
        step = await self.get_or_create_step(request_id, step_key)

        if step.status == WorkflowStepStatus.RUNNING:
            logger.debug(f"Step {step_key.value} already running for request {request_id}")
            return step

        step.status = WorkflowStepStatus.RUNNING
        step.started_at = datetime.utcnow()
        step.attempts += 1
        step.last_error_code = None
        step.last_error_message = None

        await self.db.commit()
        logger.info(f"Started step {step_key.value} for request {request_id} (attempt {step.attempts})")
        return step

    async def complete_step(
        self,
        request_id: int,
        step_key: WorkflowStepKey,
        artifacts: Optional[Dict[str, Any]] = None
    ) -> RequestWorkflowStep:
        """
        Mark step as successful.
        """
        step = await self.get_or_create_step(request_id, step_key)

        step.status = WorkflowStepStatus.SUCCESS
        step.ended_at = datetime.utcnow()

        if artifacts:
            # Merge with existing artifacts
            existing = step.artifacts_json or {}
            existing.update(artifacts)
            step.artifacts_json = existing

        await self.db.commit()
        logger.info(f"Completed step {step_key.value} for request {request_id}")
        return step

    async def fail_step(
        self,
        request_id: int,
        step_key: WorkflowStepKey,
        error_code: str,
        error_message: str,
        artifacts: Optional[Dict[str, Any]] = None,
        create_action: Optional[ActionType] = None,
        action_payload: Optional[Dict[str, Any]] = None,
        action_priority: int = 50
    ) -> RequestWorkflowStep:
        """
        Mark step as failed and optionally create an action.
        """
        step = await self.get_or_create_step(request_id, step_key)

        step.status = WorkflowStepStatus.FAILED
        step.ended_at = datetime.utcnow()
        step.last_error_code = error_code
        step.last_error_message = error_message[:2000] if error_message else None

        if artifacts:
            existing = step.artifacts_json or {}
            existing.update(artifacts)
            step.artifacts_json = existing

        await self.db.commit()
        logger.warning(f"Failed step {step_key.value} for request {request_id}: {error_code}")

        # Create human-in-the-loop action if specified
        if create_action:
            await self.create_action(
                request_id=request_id,
                workflow_step_id=step.id,
                action_type=create_action,
                payload=action_payload,
                message=error_message,
                priority=action_priority
            )

            # Mark step as blocked (awaiting human action)
            step.status = WorkflowStepStatus.BLOCKED
            await self.db.commit()

        return step

    async def reset_step_for_retry(
        self,
        request_id: int,
        step_key: WorkflowStepKey
    ) -> RequestWorkflowStep:
        """
        Reset a failed/blocked step to pending for retry.
        """
        step = await self.get_or_create_step(request_id, step_key)

        step.status = WorkflowStepStatus.PENDING
        step.last_error_code = None
        step.last_error_message = None
        step.started_at = None
        step.ended_at = None

        await self.db.commit()
        logger.info(f"Reset step {step_key.value} for request {request_id} (will be attempt {step.attempts + 1})")
        return step

    async def get_request_workflow(
        self,
        request_id: int
    ) -> List[RequestWorkflowStep]:
        """
        Get all workflow steps for a request, ordered.
        """
        result = await self.db.execute(
            select(RequestWorkflowStep)
            .where(RequestWorkflowStep.request_id == request_id)
            .order_by(RequestWorkflowStep.step_order)
        )
        return list(result.scalars().all())

    # =========================================================================
    # ACTION MANAGEMENT
    # =========================================================================

    async def create_action(
        self,
        request_id: int,
        action_type: ActionType,
        workflow_step_id: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        priority: int = 50
    ) -> RequestAction:
        """
        Create a new human-in-the-loop action.
        Idempotent: updates existing open action of same type.
        """
        # Check for existing open action of same type
        result = await self.db.execute(
            select(RequestAction).where(
                and_(
                    RequestAction.request_id == request_id,
                    RequestAction.action_type == action_type,
                    RequestAction.status == ActionStatus.OPEN
                )
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing instead of creating duplicate
            existing.payload_json = payload
            existing.message = message[:2000] if message else None
            existing.workflow_step_id = workflow_step_id
            await self.db.commit()
            logger.info(f"Updated existing action {action_type.value} for request {request_id}")
            return existing

        action = RequestAction(
            request_id=request_id,
            workflow_step_id=workflow_step_id,
            action_type=action_type,
            payload_json=payload,
            message=message[:2000] if message else None,
            priority=priority
        )
        self.db.add(action)
        await self.db.commit()

        logger.info(f"Created action {action_type.value} for request {request_id}")
        return action

    async def resolve_action(
        self,
        action_id: int,
        user_id: int,
        resolution: Dict[str, Any]
    ) -> RequestAction:
        """
        Resolve an action with admin decision.
        """
        result = await self.db.execute(
            select(RequestAction).where(RequestAction.id == action_id)
        )
        action = result.scalar_one_or_none()

        if not action:
            raise ValueError(f"Action {action_id} not found")

        if action.status != ActionStatus.OPEN:
            raise ValueError(f"Action {action_id} is not open")

        action.status = ActionStatus.DONE
        action.resolved_at = datetime.utcnow()
        action.resolved_by_id = user_id
        action.resolution_json = resolution

        await self.db.commit()
        logger.info(f"Resolved action {action_id} by user {user_id}")
        return action

    async def cancel_action(
        self,
        action_id: int,
        user_id: int
    ) -> RequestAction:
        """
        Cancel/dismiss an action.
        """
        result = await self.db.execute(
            select(RequestAction).where(RequestAction.id == action_id)
        )
        action = result.scalar_one_or_none()

        if not action:
            raise ValueError(f"Action {action_id} not found")

        action.status = ActionStatus.CANCELLED
        action.resolved_at = datetime.utcnow()
        action.resolved_by_id = user_id

        await self.db.commit()
        logger.info(f"Cancelled action {action_id} by user {user_id}")
        return action

    async def get_action_by_id(
        self,
        action_id: int
    ) -> Optional[RequestAction]:
        """
        Get a single action by ID.
        """
        result = await self.db.execute(
            select(RequestAction)
            .options(selectinload(RequestAction.request))
            .where(RequestAction.id == action_id)
        )
        return result.scalar_one_or_none()

    async def get_open_actions(
        self,
        action_type: Optional[ActionType] = None,
        limit: int = 50
    ) -> List[RequestAction]:
        """
        Get all open actions, optionally filtered by type.
        """
        query = (
            select(RequestAction)
            .options(selectinload(RequestAction.request))
            .where(RequestAction.status == ActionStatus.OPEN)
            .order_by(RequestAction.priority.desc(), RequestAction.created_at)
            .limit(limit)
        )

        if action_type:
            query = query.where(RequestAction.action_type == action_type)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_request_actions(
        self,
        request_id: int
    ) -> List[RequestAction]:
        """
        Get all actions for a request.
        """
        result = await self.db.execute(
            select(RequestAction)
            .where(RequestAction.request_id == request_id)
            .order_by(RequestAction.created_at.desc())
        )
        return list(result.scalars().all())


def get_workflow_service(db: AsyncSession) -> WorkflowService:
    """Factory function for dependency injection."""
    return WorkflowService(db)
