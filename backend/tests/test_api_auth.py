"""
Tests for authentication endpoints.

Tests auth flows: register, login, /me, Plex SSO.
"""
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock

from tests.conftest import auth_headers


class TestRegister:
    """Tests for POST /api/v1/auth/register."""

    @pytest.mark.asyncio
    async def test_first_user_becomes_admin(self, client: AsyncClient):
        """First registered user becomes admin with active status."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "firstadmin",
                "password": "securepassword123",
                "email": "admin@test.com"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pending"] is False
        assert data["user"]["role"] == "admin"
        assert data["user"]["status"] == "active"
        assert "access_token" in data

    @pytest.mark.asyncio
    async def test_subsequent_user_is_pending(self, client: AsyncClient, admin_user, test_db):
        """Subsequent users are created with pending status."""
        # Ensure admin_user fixture runs first (creates first user)
        await test_db.refresh(admin_user)

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "newuser2",
                "password": "securepassword123",
                "email": "new2@test.com"
            }
        )

        assert response.status_code == 200
        data = response.json()
        # Subsequent users should be pending
        assert data["pending"] is True
        assert data["user"]["status"] == "pending"
        # Pending users get None token
        assert data.get("access_token") is None

    @pytest.mark.asyncio
    async def test_duplicate_username_fails(self, client: AsyncClient, test_user):
        """Registration fails with duplicate username."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "username": test_user.username,  # Already exists
                "password": "password123",
                "email": "unique@test.com"
            }
        )

        assert response.status_code == 400
        assert "pris" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_duplicate_email_fails(self, client: AsyncClient, test_user):
        """Registration fails with duplicate email."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "uniqueuser",
                "password": "password123",
                "email": test_user.email  # Already exists
            }
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_register_missing_fields(self, client: AsyncClient):
        """Registration fails with missing required fields."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "incomplete"
                # Missing password
            }
        )

        assert response.status_code == 422


class TestLogin:
    """Tests for POST /api/v1/auth/login."""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, test_db):
        """Valid credentials return token."""
        from argon2 import PasswordHasher
        from app.models.user import User, UserRole, UserStatus

        # Create user with known password
        ph = PasswordHasher()
        user = User(
            username="logintest",
            email="login@test.com",
            hashed_password=ph.hash("correctpassword"),
            role=UserRole.USER,
            status=UserStatus.ACTIVE
        )
        test_db.add(user)
        await test_db.commit()

        response = await client.post(
            "/api/v1/auth/login",
            data={"username": "logintest", "password": "correctpassword"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["username"] == "logintest"

    @pytest.mark.asyncio
    async def test_login_wrong_password_fails(self, client: AsyncClient, test_user):
        """Wrong password returns 401."""
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": test_user.username, "password": "wrongpassword"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user_fails(self, client: AsyncClient):
        """Non-existent user returns 401."""
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": "nobody", "password": "anypassword"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_pending_user_fails(self, client: AsyncClient, pending_user):
        """Pending users cannot login."""
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": pending_user.username, "password": "pendingpassword123"}
        )

        # Should fail - either 401 (not found/invalid) or special handling
        assert response.status_code in [401, 403]


class TestGetMe:
    """Tests for GET /api/v1/auth/me."""

    @pytest.mark.asyncio
    async def test_get_me_returns_current_user(self, client: AsyncClient, test_user, user_token):
        """Authenticated user can get their profile."""
        response = await client.get(
            "/api/v1/auth/me",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == test_user.username
        assert data["email"] == test_user.email
        assert data["role"] == "user"

    @pytest.mark.asyncio
    async def test_get_me_admin_user(self, client: AsyncClient, admin_user, admin_token):
        """Admin user can get their profile."""
        response = await client.get(
            "/api/v1/auth/me",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == admin_user.username
        assert data["role"] == "admin"

    @pytest.mark.asyncio
    async def test_get_me_without_token_fails(self, client: AsyncClient):
        """Request without token returns 401."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_invalid_token_fails(self, client: AsyncClient):
        """Request with invalid token returns 401."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token-here"}
        )
        assert response.status_code == 401


class TestUpdateMe:
    """Tests for PATCH /api/v1/auth/me."""

    @pytest.mark.asyncio
    async def test_update_email(self, client: AsyncClient, test_user, user_token):
        """User can update their email."""
        response = await client.patch(
            "/api/v1/auth/me",
            json={"email": "newemail@test.com"},
            headers=auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newemail@test.com"

    @pytest.mark.asyncio
    async def test_update_without_auth_fails(self, client: AsyncClient):
        """Update without auth returns 401."""
        response = await client.patch(
            "/api/v1/auth/me",
            json={"email": "newemail@test.com"}
        )
        assert response.status_code == 401


class TestUserStats:
    """Tests for GET /api/v1/auth/stats."""

    @pytest.mark.asyncio
    async def test_get_stats_returns_request_counts(self, client: AsyncClient, test_user, user_token):
        """User can get their request statistics."""
        response = await client.get(
            "/api/v1/auth/stats",
            headers=auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert "requests_remaining" in data

    @pytest.mark.asyncio
    async def test_get_stats_without_auth_fails(self, client: AsyncClient):
        """Stats without auth returns 401."""
        response = await client.get("/api/v1/auth/stats")
        assert response.status_code == 401


class TestPlexSSO:
    """Tests for POST /api/v1/auth/plex."""

    @pytest.mark.asyncio
    async def test_plex_auth_creates_new_user(
        self, client: AsyncClient, mock_plex_user_response
    ):
        """Plex SSO creates new user on first login."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            # Mock Plex user account call
            user_response = MagicMock()
            user_response.status_code = 200
            user_response.json.return_value = mock_plex_user_response
            user_response.raise_for_status = MagicMock()
            mock_instance.get.return_value = user_response

            # Mock config service (inline import in auth.py)
            with patch("app.services.service_config_service.get_service_config_service") as mock_config:
                mock_config_instance = MagicMock()
                mock_config_instance.get_service_config = AsyncMock(return_value=None)
                mock_config.return_value = mock_config_instance

                response = await client.post(
                    "/api/v1/auth/plex",
                    json={"plex_token": "test-plex-token"}
                )

        # First user becomes admin with token, or new user is pending
        assert response.status_code == 200
        data = response.json()
        # Either we get a token (first user/admin) or pending status
        assert "access_token" in data or data.get("pending") is True

    @pytest.mark.asyncio
    async def test_plex_auth_invalid_token_fails(self, client: AsyncClient):
        """Invalid Plex token returns error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            # Mock failed Plex API call
            error_response = MagicMock()
            error_response.status_code = 401
            error_response.raise_for_status.side_effect = Exception("Unauthorized")
            mock_instance.get.return_value = error_response

            response = await client.post(
                "/api/v1/auth/plex",
                json={"plex_token": "invalid-token"}
            )

        assert response.status_code in [401, 400, 500]
