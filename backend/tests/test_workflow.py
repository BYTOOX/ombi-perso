"""
Tests for workflow models and service.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.workflow import (
    RequestWorkflowStep, RequestAction,
    WorkflowStepKey, WorkflowStepStatus,
    ActionType, ActionStatus
)
from app.services.workflow_service import WorkflowService


@pytest.fixture
def mock_db():
    """Create mock async database session with proper async handling."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    # Default execute returns a mock result
    db.execute = AsyncMock()
    return db


def create_mock_result(return_value):
    """Helper to create a properly configured mock result for async db queries."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = return_value
    mock_result.scalars.return_value.all.return_value = []
    return mock_result


@pytest.fixture
def workflow_service(mock_db):
    """Create workflow service with mock db."""
    return WorkflowService(mock_db)


class TestWorkflowStepCreation:
    """Test workflow step creation and status updates."""

    @pytest.mark.asyncio
    async def test_get_or_create_step_creates_new(self, workflow_service, mock_db):
        """Test that get_or_create_step creates a new step when none exists."""
        # Mock: no existing step found
        mock_db.execute.return_value = create_mock_result(None)

        step = await workflow_service.get_or_create_step(
            request_id=1,
            step_key=WorkflowStepKey.TORRENT_SEARCH
        )

        # Verify step was created with correct attributes
        mock_db.add.assert_called_once()
        added_step = mock_db.add.call_args[0][0]
        assert added_step.request_id == 1
        assert added_step.step_key == WorkflowStepKey.TORRENT_SEARCH
        assert added_step.status == WorkflowStepStatus.PENDING
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_create_step_returns_existing(self, workflow_service, mock_db):
        """Test that get_or_create_step returns existing step."""
        # Mock: existing step found
        existing_step = MagicMock(spec=RequestWorkflowStep)
        existing_step.request_id = 1
        existing_step.step_key = WorkflowStepKey.TORRENT_SEARCH

        mock_db.execute.return_value = create_mock_result(existing_step)

        step = await workflow_service.get_or_create_step(
            request_id=1,
            step_key=WorkflowStepKey.TORRENT_SEARCH
        )

        # Verify no new step was added
        mock_db.add.assert_not_called()
        assert step == existing_step

    @pytest.mark.asyncio
    async def test_start_step_updates_status(self, workflow_service, mock_db):
        """Test that start_step marks step as running."""
        # Mock existing step in PENDING state
        existing_step = MagicMock(spec=RequestWorkflowStep)
        existing_step.status = WorkflowStepStatus.PENDING
        existing_step.attempts = 0

        mock_db.execute.return_value = create_mock_result(existing_step)

        step = await workflow_service.start_step(
            request_id=1,
            step_key=WorkflowStepKey.TORRENT_SEARCH
        )

        # Verify step was updated
        assert step.status == WorkflowStepStatus.RUNNING
        assert step.attempts == 1
        assert step.started_at is not None
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_fail_step_with_action_creates_blocked_step(self, workflow_service, mock_db):
        """Test that failing a step with action creation marks it as BLOCKED."""
        # Mock: no existing step found (will create new), then no existing action
        mock_db.execute.return_value = create_mock_result(None)

        step = await workflow_service.fail_step(
            request_id=1,
            step_key=WorkflowStepKey.TORRENT_SEARCH,
            error_code="NO_RESULTS",
            error_message="No torrents found for: Test Movie 2024",
            artifacts={"query": "Test Movie 2024", "results_count": 0},
            create_action=ActionType.FIX_SEARCH_QUERY,
            action_payload={
                "original_query": "Test Movie 2024",
                "title": "Test Movie",
                "year": 2024
            }
        )

        # Verify step status is BLOCKED (due to action creation)
        added_items = [call[0][0] for call in mock_db.add.call_args_list]

        # First add should be the step
        step_added = added_items[0]
        assert step_added.request_id == 1
        assert step_added.step_key == WorkflowStepKey.TORRENT_SEARCH

        # Second add should be the action
        action_added = added_items[1]
        assert action_added.request_id == 1
        assert action_added.action_type == ActionType.FIX_SEARCH_QUERY

        # Multiple commits for step creation, failure, and action creation
        assert mock_db.commit.call_count >= 2


class TestActionManagement:
    """Test action creation and resolution."""

    @pytest.mark.asyncio
    async def test_create_action_new(self, workflow_service, mock_db):
        """Test creating a new action."""
        # Mock: no existing action found
        mock_db.execute.return_value = create_mock_result(None)

        action = await workflow_service.create_action(
            request_id=1,
            action_type=ActionType.FIX_SEARCH_QUERY,
            payload={"original_query": "Test"},
            message="Test message",
            priority=70
        )

        # Verify action was added
        mock_db.add.assert_called_once()
        added_action = mock_db.add.call_args[0][0]
        assert added_action.request_id == 1
        assert added_action.action_type == ActionType.FIX_SEARCH_QUERY
        assert added_action.priority == 70

    @pytest.mark.asyncio
    async def test_create_action_updates_existing(self, workflow_service, mock_db):
        """Test that create_action updates existing open action (idempotent)."""
        # Mock: existing open action found
        existing_action = MagicMock(spec=RequestAction)
        existing_action.request_id = 1
        existing_action.action_type = ActionType.FIX_SEARCH_QUERY
        existing_action.status = ActionStatus.OPEN

        mock_db.execute.return_value = create_mock_result(existing_action)

        action = await workflow_service.create_action(
            request_id=1,
            action_type=ActionType.FIX_SEARCH_QUERY,
            payload={"new_query": "Updated"},
            message="Updated message"
        )

        # Verify existing action was updated, not a new one added
        mock_db.add.assert_not_called()
        assert action.payload_json == {"new_query": "Updated"}
        assert action.message == "Updated message"

    @pytest.mark.asyncio
    async def test_resolve_action_success(self, workflow_service, mock_db):
        """Test resolving an action successfully."""
        # Mock existing open action
        mock_action = MagicMock(spec=RequestAction)
        mock_action.id = 1
        mock_action.request_id = 1
        mock_action.action_type = ActionType.FIX_SEARCH_QUERY
        mock_action.status = ActionStatus.OPEN
        mock_action.payload_json = {"original_query": "Test Movie"}

        mock_db.execute.return_value = create_mock_result(mock_action)

        # Resolve with new query
        resolved = await workflow_service.resolve_action(
            action_id=1,
            user_id=99,
            resolution={"new_query": "Test Movie 2024 FRENCH"}
        )

        # Verify action was updated
        assert mock_action.status == ActionStatus.DONE
        assert mock_action.resolved_by_id == 99
        assert mock_action.resolution_json == {"new_query": "Test Movie 2024 FRENCH"}
        assert mock_action.resolved_at is not None
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_resolve_already_resolved_action_fails(self, workflow_service, mock_db):
        """Test that resolving an already-resolved action raises error."""
        # Mock action that's already done
        mock_action = MagicMock(spec=RequestAction)
        mock_action.id = 1
        mock_action.status = ActionStatus.DONE

        mock_db.execute.return_value = create_mock_result(mock_action)

        # Should raise ValueError
        with pytest.raises(ValueError, match="not open"):
            await workflow_service.resolve_action(
                action_id=1,
                user_id=99,
                resolution={}
            )

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_action_fails(self, workflow_service, mock_db):
        """Test that resolving a non-existent action raises error."""
        # Mock: no action found
        mock_db.execute.return_value = create_mock_result(None)

        # Should raise ValueError
        with pytest.raises(ValueError, match="not found"):
            await workflow_service.resolve_action(
                action_id=999,
                user_id=99,
                resolution={}
            )

    @pytest.mark.asyncio
    async def test_cancel_action_success(self, workflow_service, mock_db):
        """Test cancelling an action."""
        # Mock existing open action
        mock_action = MagicMock(spec=RequestAction)
        mock_action.id = 1
        mock_action.status = ActionStatus.OPEN

        mock_db.execute.return_value = create_mock_result(mock_action)

        cancelled = await workflow_service.cancel_action(
            action_id=1,
            user_id=99
        )

        # Verify action was cancelled
        assert mock_action.status == ActionStatus.CANCELLED
        assert mock_action.resolved_by_id == 99
        assert mock_action.resolved_at is not None


class TestWorkflowStepOrder:
    """Test step ordering functionality."""

    def test_step_order_values(self):
        """Test that step order values are correctly defined."""
        assert WorkflowService.STEP_ORDER[WorkflowStepKey.METADATA] == 1
        assert WorkflowService.STEP_ORDER[WorkflowStepKey.TORRENT_SEARCH] == 2
        assert WorkflowService.STEP_ORDER[WorkflowStepKey.TORRENT_PICK] == 3
        assert WorkflowService.STEP_ORDER[WorkflowStepKey.RENAME] == 7
        assert WorkflowService.STEP_ORDER[WorkflowStepKey.PLEX_SCAN] == 9
        assert WorkflowService.STEP_ORDER[WorkflowStepKey.VERIFY] == 10


class TestWorkflowStepModel:
    """Test WorkflowStep model properties."""

    def test_duration_seconds_with_both_times(self):
        """Test duration calculation when both times are set."""
        step = RequestWorkflowStep()
        step.started_at = datetime(2024, 1, 1, 12, 0, 0)
        step.ended_at = datetime(2024, 1, 1, 12, 0, 30)

        assert step.duration_seconds == 30.0

    def test_duration_seconds_without_end_time(self):
        """Test duration is None when end time not set."""
        step = RequestWorkflowStep()
        step.started_at = datetime(2024, 1, 1, 12, 0, 0)
        step.ended_at = None

        assert step.duration_seconds is None
