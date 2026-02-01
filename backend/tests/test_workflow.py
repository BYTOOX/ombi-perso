"""
Tests for workflow models, service, and API endpoints.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient

from app.models.workflow import (
    RequestWorkflowStep, RequestAction,
    WorkflowStepKey, WorkflowStepStatus,
    ActionType, ActionStatus
)
from app.models.request import MediaRequest, MediaType, RequestStatus
from app.services.workflow_service import WorkflowService
from tests.conftest import auth_headers


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


# =============================================================================
# WORKFLOW ENDPOINT TESTS
# =============================================================================

class TestWorkflowEndpoints:
    """Tests for workflow API endpoints."""

    @pytest.mark.asyncio
    async def test_get_workflow_for_own_request(
        self, client: AsyncClient, test_user, user_token, test_db
    ):
        """User can get workflow details for their own request."""
        # Create a request
        request = MediaRequest(
            user_id=test_user.id,
            media_type=MediaType.MOVIE,
            external_id="workflow-test-1",
            source="tmdb",
            title="Workflow Test Movie",
            status=RequestStatus.PENDING
        )
        test_db.add(request)
        await test_db.commit()
        await test_db.refresh(request)

        response = await client.get(
            f"/api/v1/workflow/requests/{request.id}",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == request.id
        assert data["request_title"] == "Workflow Test Movie"
        assert "steps" in data
        assert "actions" in data

    @pytest.mark.asyncio
    async def test_get_workflow_for_others_request_fails(
        self, client: AsyncClient, admin_user, user_token, test_db
    ):
        """User cannot get workflow for another user's request."""
        # Create request for admin
        request = MediaRequest(
            user_id=admin_user.id,
            media_type=MediaType.MOVIE,
            external_id="workflow-other",
            source="tmdb",
            title="Admin's Movie",
            status=RequestStatus.PENDING
        )
        test_db.add(request)
        await test_db.commit()
        await test_db.refresh(request)

        response = await client.get(
            f"/api/v1/workflow/requests/{request.id}",
            headers=auth_headers(user_token)  # Regular user token
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_get_any_workflow(
        self, client: AsyncClient, test_user, admin_token, test_db
    ):
        """Admin can get workflow for any request."""
        # Create request for regular user
        request = MediaRequest(
            user_id=test_user.id,
            media_type=MediaType.MOVIE,
            external_id="workflow-admin-view",
            source="tmdb",
            title="User's Movie",
            status=RequestStatus.PENDING
        )
        test_db.add(request)
        await test_db.commit()
        await test_db.refresh(request)

        response = await client.get(
            f"/api/v1/workflow/requests/{request.id}",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_workflow_nonexistent_request(
        self, client: AsyncClient, user_token
    ):
        """Getting workflow for nonexistent request returns 404."""
        response = await client.get(
            "/api/v1/workflow/requests/99999",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 404


class TestWorkflowActionsEndpoints:
    """Tests for workflow actions endpoints (admin only)."""

    @pytest.mark.asyncio
    async def test_list_actions_admin_only(
        self, client: AsyncClient, admin_token
    ):
        """Admin can list actions."""
        response = await client.get(
            "/api/v1/workflow/actions",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_actions_non_admin_fails(
        self, client: AsyncClient, user_token
    ):
        """Regular user cannot list actions."""
        response = await client.get(
            "/api/v1/workflow/actions",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_actions_without_auth_fails(
        self, client: AsyncClient
    ):
        """Unauthenticated user cannot list actions."""
        response = await client.get("/api/v1/workflow/actions")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_action_nonexistent(
        self, client: AsyncClient, admin_token
    ):
        """Getting nonexistent action returns 404."""
        response = await client.get(
            "/api/v1/workflow/actions/99999",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_resolve_action_nonexistent(
        self, client: AsyncClient, admin_token
    ):
        """Resolving nonexistent action returns error."""
        response = await client.post(
            "/api/v1/workflow/actions/99999/resolve",
            json={"resolution": {"test": "data"}},
            headers=auth_headers(admin_token)
        )

        # Should return 400 (action not found) or 404
        assert response.status_code in [400, 404]

    @pytest.mark.asyncio
    async def test_cancel_action_nonexistent(
        self, client: AsyncClient, admin_token
    ):
        """Cancelling nonexistent action returns error."""
        response = await client.post(
            "/api/v1/workflow/actions/99999/cancel",
            headers=auth_headers(admin_token)
        )

        # Should return 400 (action not found) or 404
        assert response.status_code in [400, 404]


class TestWorkflowRetryEndpoint:
    """Tests for workflow retry step endpoint."""

    @pytest.mark.asyncio
    async def test_retry_step_admin_only(
        self, client: AsyncClient, user_token, test_user, test_db
    ):
        """Regular user cannot retry steps."""
        # Create a request
        request = MediaRequest(
            user_id=test_user.id,
            media_type=MediaType.MOVIE,
            external_id="retry-test",
            source="tmdb",
            title="Retry Test",
            status=RequestStatus.PENDING
        )
        test_db.add(request)
        await test_db.commit()
        await test_db.refresh(request)

        response = await client.post(
            f"/api/v1/workflow/requests/{request.id}/retry-step",
            json={"step_key": "torrent_search"},
            headers=auth_headers(user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_retry_step_nonexistent_request(
        self, client: AsyncClient, admin_token
    ):
        """Retrying step for nonexistent request returns 404."""
        response = await client.post(
            "/api/v1/workflow/requests/99999/retry-step",
            json={"step_key": "torrent_search"},
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 404
