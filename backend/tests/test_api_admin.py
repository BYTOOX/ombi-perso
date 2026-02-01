"""
Tests for admin endpoints.

Tests admin-only access control and user management.
"""
import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock, AsyncMock

from tests.conftest import auth_headers
from app.models.user import User, UserRole, UserStatus


class TestAdminAccessControl:
    """Tests for admin-only endpoint access."""

    @pytest.mark.asyncio
    async def test_admin_stats_requires_admin(self, client: AsyncClient, user_token):
        """Regular users cannot access admin stats."""
        response = await client.get(
            "/api/v1/admin/stats",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_get_stats(self, client: AsyncClient, admin_token):
        """Admin users can access stats endpoint."""
        with patch("app.api.v1.admin.get_downloader_service") as mock_dl:
            mock_dl_instance = MagicMock()
            mock_dl_instance.get_disk_usage.return_value = {
                "free_space": 500_000_000_000,
                "total_space": 1_000_000_000_000
            }
            mock_dl_instance.get_all_torrents.return_value = []
            mock_dl.return_value = mock_dl_instance

            response = await client.get(
                "/api/v1/admin/stats",
                headers=auth_headers(admin_token)
            )

        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "requests" in data

    @pytest.mark.asyncio
    async def test_admin_endpoint_without_auth_fails(self, client: AsyncClient):
        """Admin endpoints require authentication."""
        response = await client.get("/api/v1/admin/stats")
        assert response.status_code == 401


class TestUserManagement:
    """Tests for user management endpoints."""

    @pytest.mark.asyncio
    async def test_list_users_admin_only(self, client: AsyncClient, admin_token):
        """Admin can list all users."""
        response = await client.get(
            "/api/v1/admin/users",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_list_users_non_admin_fails(self, client: AsyncClient, user_token):
        """Non-admin cannot list users."""
        response = await client.get(
            "/api/v1/admin/users",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_approve_pending_user(
        self, client: AsyncClient, admin_token, pending_user, test_db
    ):
        """Admin can approve pending users."""
        response = await client.post(
            f"/api/v1/admin/users/{pending_user.id}/approve",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_approve_already_active_user(
        self, client: AsyncClient, admin_token, test_user
    ):
        """Approving already active user should still work or return sensible response."""
        response = await client.post(
            f"/api/v1/admin/users/{test_user.id}/approve",
            headers=auth_headers(admin_token)
        )

        # Should not fail - user is already active
        assert response.status_code in [200, 400]

    @pytest.mark.asyncio
    async def test_reject_user(
        self, client: AsyncClient, admin_token, pending_user
    ):
        """Admin can reject a pending user."""
        response = await client.post(
            f"/api/v1/admin/users/{pending_user.id}/reject",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_cannot_delete_self(
        self, client: AsyncClient, admin_user, admin_token
    ):
        """Admin cannot delete their own account."""
        response = await client.delete(
            f"/api/v1/admin/users/{admin_user.id}",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_other_user(
        self, client: AsyncClient, admin_token, test_user
    ):
        """Admin can delete other users."""
        response = await client.delete(
            f"/api/v1/admin/users/{test_user.id}",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user(
        self, client: AsyncClient, admin_token
    ):
        """Deleting non-existent user returns 404."""
        response = await client.delete(
            "/api/v1/admin/users/99999",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_user_cannot_approve(
        self, client: AsyncClient, user_token, pending_user
    ):
        """Regular user cannot approve others."""
        response = await client.post(
            f"/api/v1/admin/users/{pending_user.id}/approve",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 403


class TestAdminHealth:
    """Tests for admin health check endpoint."""

    @pytest.mark.asyncio
    async def test_admin_health_check(self, client: AsyncClient, admin_token):
        """Admin health endpoint uses HealthCheckService."""
        with patch("app.api.v1.admin.get_healthcheck_service") as mock_hc:
            mock_result = MagicMock(status="ok", message="OK", latency_ms=50)
            mock_results = {
                "plex": mock_result,
                "qbittorrent": mock_result,
                "ai": mock_result,
            }
            mock_instance = MagicMock()
            mock_instance.check_all_services = AsyncMock(return_value=mock_results)
            mock_hc.return_value = mock_instance

            response = await client.get(
                "/api/v1/admin/health",
                headers=auth_headers(admin_token)
            )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Database always present
        assert "database" in data
        assert data["database"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_admin_health_returns_all_services(self, client: AsyncClient, admin_token):
        """Admin health returns all services from HealthCheckService."""
        with patch("app.api.v1.admin.get_healthcheck_service") as mock_hc:
            mock_result = MagicMock(status="ok", message="OK", latency_ms=50)
            mock_results = {
                "plex": mock_result,
                "qbittorrent": mock_result,
                "ai": mock_result,
                "tmdb": mock_result,
                "ygg": mock_result,
                "discord": mock_result,
                "flaresolverr": mock_result
            }
            mock_instance = MagicMock()
            mock_instance.check_all_services = AsyncMock(return_value=mock_results)
            mock_hc.return_value = mock_instance

            response = await client.get(
                "/api/v1/admin/health",
                headers=auth_headers(admin_token)
            )

        assert response.status_code == 200
        data = response.json()

        # All services must be present
        for service in ["plex", "qbittorrent", "ai", "database"]:
            assert service in data

    @pytest.mark.asyncio
    async def test_admin_health_no_ollama_key(self, client: AsyncClient, admin_token):
        """Admin health should return 'ai', not 'ollama'."""
        with patch("app.api.v1.admin.get_healthcheck_service") as mock_hc:
            mock_instance = MagicMock()
            mock_instance.check_all_services = AsyncMock(return_value={
                "ai": MagicMock(status="ok", message="OK", latency_ms=50)
            })
            mock_hc.return_value = mock_instance

            response = await client.get(
                "/api/v1/admin/health",
                headers=auth_headers(admin_token)
            )

        data = response.json()
        assert "ollama" not in data
        assert "ai" in data

    @pytest.mark.asyncio
    async def test_admin_health_non_admin_fails(self, client: AsyncClient, user_token):
        """Regular user cannot access admin health."""
        response = await client.get(
            "/api/v1/admin/health",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 403


class TestAdminEndpointsAccess:
    """Tests for admin endpoint access patterns."""

    @pytest.mark.asyncio
    async def test_admin_users_list_requires_admin(self, client: AsyncClient, user_token):
        """Regular user cannot access admin user list."""
        response = await client.get(
            "/api/v1/admin/users",
            headers=auth_headers(user_token)
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_users_list_requires_auth(self, client: AsyncClient):
        """User list requires authentication."""
        response = await client.get("/api/v1/admin/users")
        assert response.status_code == 401
