"""
Tests for request endpoints.

Tests request lifecycle: create, list, get, delete.
"""
import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock, AsyncMock

from tests.conftest import auth_headers
from app.models.request import MediaRequest, MediaType, RequestStatus


class TestCreateRequest:
    """Tests for POST /api/v1/requests."""

    @pytest.mark.asyncio
    async def test_create_request_success(self, client: AsyncClient, test_user, user_token, app):
        """Authenticated user can create a request."""
        from app.dependencies import get_plex_manager_service, get_notification_service

        # Create mock services
        mock_plex = MagicMock()
        mock_plex.check_exists = MagicMock(return_value={"exists": False})

        mock_notif = AsyncMock()
        mock_notif.notify_request_created = AsyncMock()

        # Override dependencies
        app.dependency_overrides[get_plex_manager_service] = lambda: mock_plex
        app.dependency_overrides[get_notification_service] = lambda: mock_notif

        with patch("app.workers.request_worker.process_request_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-123")

            response = await client.post(
                "/api/v1/requests",
                json={
                    "media_type": "movie",
                    "external_id": "550",
                    "source": "tmdb",
                    "title": "Fight Club",
                    "year": 1999,
                    "quality_preference": "1080p"
                },
                headers=auth_headers(user_token)
            )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Fight Club"
        assert data["status"] == "pending"
        assert data["user_id"] == test_user.id
        assert data["media_type"] == "movie"

    @pytest.mark.asyncio
    async def test_create_request_without_auth_fails(self, client: AsyncClient):
        """Request creation requires authentication."""
        response = await client.post(
            "/api/v1/requests",
            json={
                "media_type": "movie",
                "external_id": "550",
                "source": "tmdb",
                "title": "Fight Club",
                "year": 1999
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_request_invalid_media_type(self, client: AsyncClient, user_token):
        """Invalid media type returns 422."""
        response = await client.post(
            "/api/v1/requests",
            json={
                "media_type": "invalid_type",
                "external_id": "550",
                "source": "tmdb",
                "title": "Test"
            },
            headers=auth_headers(user_token)
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_request_missing_title(self, client: AsyncClient, user_token):
        """Missing title returns 422."""
        response = await client.post(
            "/api/v1/requests",
            json={
                "media_type": "movie",
                "external_id": "550",
                "source": "tmdb"
                # Missing title
            },
            headers=auth_headers(user_token)
        )

        assert response.status_code == 422


class TestListRequests:
    """Tests for GET /api/v1/requests."""

    @pytest.mark.asyncio
    async def test_list_own_requests(self, client: AsyncClient, test_user, user_token, test_db):
        """Regular users see only their own requests."""
        # Create a request for this user
        request = MediaRequest(
            user_id=test_user.id,
            media_type=MediaType.MOVIE,
            external_id="123",
            source="tmdb",
            title="User Request",
            status=RequestStatus.PENDING
        )
        test_db.add(request)
        await test_db.commit()

        response = await client.get(
            "/api/v1/requests",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert all(r["user_id"] == test_user.id for r in data["items"])

    @pytest.mark.asyncio
    async def test_admin_sees_all_requests(
        self, client: AsyncClient, admin_user, admin_token, test_user, test_db
    ):
        """Admin users can see all requests."""
        # Create requests for different users
        for user, title in [(admin_user, "Admin Request"), (test_user, "User Request")]:
            request = MediaRequest(
                user_id=user.id,
                media_type=MediaType.MOVIE,
                external_id=f"ext-{user.id}",
                source="tmdb",
                title=title,
                status=RequestStatus.PENDING
            )
            test_db.add(request)
        await test_db.commit()

        response = await client.get(
            "/api/v1/requests",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2

    @pytest.mark.asyncio
    async def test_list_requests_pagination(self, client: AsyncClient, test_user, user_token, test_db):
        """Request list supports pagination."""
        # Create multiple requests
        for i in range(5):
            request = MediaRequest(
                user_id=test_user.id,
                media_type=MediaType.MOVIE,
                external_id=f"movie-{i}",
                source="tmdb",
                title=f"Movie {i}",
                status=RequestStatus.PENDING
            )
            test_db.add(request)
        await test_db.commit()

        response = await client.get(
            "/api/v1/requests?page=1&page_size=2",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2
        assert "total_pages" in data

    @pytest.mark.asyncio
    async def test_list_requests_without_auth_fails(self, client: AsyncClient):
        """Request list requires authentication."""
        response = await client.get("/api/v1/requests")
        assert response.status_code == 401


class TestGetRequest:
    """Tests for GET /api/v1/requests/{id}."""

    @pytest.mark.asyncio
    async def test_get_own_request(self, client: AsyncClient, test_user, user_token, test_db):
        """User can get their own request details."""
        request = MediaRequest(
            user_id=test_user.id,
            media_type=MediaType.MOVIE,
            external_id="456",
            source="tmdb",
            title="My Movie",
            status=RequestStatus.PENDING
        )
        test_db.add(request)
        await test_db.commit()
        await test_db.refresh(request)

        response = await client.get(
            f"/api/v1/requests/{request.id}",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 200
        assert response.json()["title"] == "My Movie"

    @pytest.mark.asyncio
    async def test_cannot_get_others_request(
        self, client: AsyncClient, admin_user, test_user, user_token, test_db
    ):
        """User cannot access another user's request."""
        # Create request for admin
        request = MediaRequest(
            user_id=admin_user.id,
            media_type=MediaType.MOVIE,
            external_id="789",
            source="tmdb",
            title="Admin Movie",
            status=RequestStatus.PENDING
        )
        test_db.add(request)
        await test_db.commit()
        await test_db.refresh(request)

        response = await client.get(
            f"/api/v1/requests/{request.id}",
            headers=auth_headers(user_token)  # Regular user token
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_get_any_request(
        self, client: AsyncClient, test_user, admin_token, test_db
    ):
        """Admin can access any user's request."""
        request = MediaRequest(
            user_id=test_user.id,
            media_type=MediaType.MOVIE,
            external_id="user-movie",
            source="tmdb",
            title="User Movie",
            status=RequestStatus.PENDING
        )
        test_db.add(request)
        await test_db.commit()
        await test_db.refresh(request)

        response = await client.get(
            f"/api/v1/requests/{request.id}",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_nonexistent_request(self, client: AsyncClient, user_token):
        """Non-existent request returns 404."""
        response = await client.get(
            "/api/v1/requests/99999",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 404


class TestDeleteRequest:
    """Tests for DELETE /api/v1/requests/{id}."""

    @pytest.mark.asyncio
    async def test_user_can_delete_own_pending_request(
        self, client: AsyncClient, test_user, user_token, test_db
    ):
        """User can delete their own pending request."""
        request = MediaRequest(
            user_id=test_user.id,
            media_type=MediaType.MOVIE,
            external_id="delete-me",
            source="tmdb",
            title="Delete Me",
            status=RequestStatus.PENDING
        )
        test_db.add(request)
        await test_db.commit()
        await test_db.refresh(request)

        response = await client.delete(
            f"/api/v1/requests/{request.id}",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_cannot_delete_others_request(
        self, client: AsyncClient, admin_user, user_token, test_db
    ):
        """User cannot delete another user's request."""
        request = MediaRequest(
            user_id=admin_user.id,
            media_type=MediaType.MOVIE,
            external_id="not-yours",
            source="tmdb",
            title="Not Yours",
            status=RequestStatus.PENDING
        )
        test_db.add(request)
        await test_db.commit()
        await test_db.refresh(request)

        response = await client.delete(
            f"/api/v1/requests/{request.id}",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_delete_any_request(
        self, client: AsyncClient, test_user, admin_token, test_db
    ):
        """Admin can delete any request."""
        request = MediaRequest(
            user_id=test_user.id,
            media_type=MediaType.MOVIE,
            external_id="admin-delete",
            source="tmdb",
            title="Admin Delete",
            status=RequestStatus.PENDING
        )
        test_db.add(request)
        await test_db.commit()
        await test_db.refresh(request)

        response = await client.delete(
            f"/api/v1/requests/{request.id}",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200


class TestRequestApproval:
    """Tests for POST /api/v1/requests/{id}/approve and /reject."""

    @pytest.mark.asyncio
    async def test_admin_can_approve_request(
        self, client: AsyncClient, test_user, admin_token, test_db
    ):
        """Admin can approve a request."""
        request = MediaRequest(
            user_id=test_user.id,
            media_type=MediaType.MOVIE,
            external_id="approve-me",
            source="tmdb",
            title="Approve Me",
            status=RequestStatus.AWAITING_APPROVAL
        )
        test_db.add(request)
        await test_db.commit()
        await test_db.refresh(request)

        with patch("app.workers.request_worker.process_request_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-approve")

            response = await client.post(
                f"/api/v1/requests/{request.id}/approve",
                headers=auth_headers(admin_token)
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_user_cannot_approve_request(
        self, client: AsyncClient, test_user, user_token, test_db
    ):
        """Regular user cannot approve requests."""
        request = MediaRequest(
            user_id=test_user.id,
            media_type=MediaType.MOVIE,
            external_id="no-approve",
            source="tmdb",
            title="No Approve",
            status=RequestStatus.AWAITING_APPROVAL
        )
        test_db.add(request)
        await test_db.commit()
        await test_db.refresh(request)

        response = await client.post(
            f"/api/v1/requests/{request.id}/approve",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_delete_request(
        self, client: AsyncClient, test_user, admin_token, test_db
    ):
        """Admin can delete (cancel) a request instead of reject endpoint."""
        request = MediaRequest(
            user_id=test_user.id,
            media_type=MediaType.MOVIE,
            external_id="cancel-me",
            source="tmdb",
            title="Cancel Me",
            status=RequestStatus.AWAITING_APPROVAL
        )
        test_db.add(request)
        await test_db.commit()
        await test_db.refresh(request)

        response = await client.delete(
            f"/api/v1/requests/{request.id}",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200
