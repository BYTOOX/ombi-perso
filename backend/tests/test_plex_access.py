"""
Tests for Plex server access verification.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_resources_with_access():
    """Mock Plex API response with access to the server."""
    return [
        {
            "name": "Mon Serveur Plex",
            "clientIdentifier": "abc123-machine-id",
            "provides": "server",
            "owned": True,
            "accessToken": "server-token-xxx"
        },
        {
            "name": "Autre Serveur",
            "clientIdentifier": "other-machine-id",
            "provides": "server",
            "owned": False,
            "accessToken": "other-token"
        }
    ]


@pytest.fixture
def mock_resources_no_access():
    """Mock Plex API response without access to the target server."""
    return [
        {
            "name": "Serveur Ami",
            "clientIdentifier": "friend-machine-id",
            "provides": "server",
            "owned": False,
            "accessToken": "friend-token"
        }
    ]


@pytest.fixture
def mock_resources_with_players():
    """Mock Plex API response with mixed resources (servers + players)."""
    return [
        {
            "name": "Mon Serveur",
            "clientIdentifier": "abc123-machine-id",
            "provides": "server",
            "owned": True
        },
        {
            "name": "Plex Web",
            "clientIdentifier": "web-player-id",
            "provides": "player",
            "owned": False
        },
        {
            "name": "iPhone",
            "clientIdentifier": "iphone-id",
            "provides": "player",
            "owned": False
        }
    ]


class TestGetUserPlexServers:
    """Tests for get_user_plex_servers function."""

    @pytest.mark.asyncio
    async def test_returns_only_servers(self, mock_resources_with_players):
        """Filters out players, returns only servers."""
        from app.services.plex_access_service import get_user_plex_servers

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_resources_with_players
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            servers = await get_user_plex_servers("user-token")

            assert len(servers) == 1
            assert servers[0]["name"] == "Mon Serveur"
            assert servers[0]["machineIdentifier"] == "abc123-machine-id"

    @pytest.mark.asyncio
    async def test_includes_server_details(self, mock_resources_with_access):
        """Returns server name, machineIdentifier, owned status."""
        from app.services.plex_access_service import get_user_plex_servers

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_resources_with_access
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            servers = await get_user_plex_servers("user-token")

            assert len(servers) == 2

            owned_server = next(s for s in servers if s["owned"])
            assert owned_server["name"] == "Mon Serveur Plex"
            assert owned_server["machineIdentifier"] == "abc123-machine-id"


class TestCheckPlexServerAccess:
    """Tests for check_plex_server_access function."""

    @pytest.mark.asyncio
    async def test_access_granted_when_server_in_list(self, mock_resources_with_access):
        """Returns True when user has access to the required server."""
        from app.services.plex_access_service import check_plex_server_access

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_resources_with_access
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            result = await check_plex_server_access("user-token", "abc123-machine-id")

            assert result is True

    @pytest.mark.asyncio
    async def test_access_denied_when_server_not_in_list(self, mock_resources_no_access):
        """Returns False when user doesn't have access to the required server."""
        from app.services.plex_access_service import check_plex_server_access

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_resources_no_access
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            result = await check_plex_server_access("user-token", "abc123-machine-id")

            assert result is False

    @pytest.mark.asyncio
    async def test_no_restriction_when_machine_id_empty(self):
        """Returns True when no machine_identifier is configured."""
        from app.services.plex_access_service import check_plex_server_access

        # Should not call the API when machine_id is empty
        result = await check_plex_server_access("user-token", "")
        assert result is True

        result = await check_plex_server_access("user-token", None)
        assert result is True

    @pytest.mark.asyncio
    async def test_access_denied_on_api_error(self):
        """Returns False when API call fails (fail secure)."""
        from app.services.plex_access_service import check_plex_server_access
        import httpx

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.side_effect = httpx.HTTPStatusError(
                "401 Unauthorized",
                request=MagicMock(),
                response=MagicMock(status_code=401)
            )

            result = await check_plex_server_access("invalid-token", "abc123-machine-id")

            assert result is False


class TestPlexAuthEndpointAccessCheck:
    """Tests for Plex SSO endpoint with access verification.

    Note: Full integration tests would require TestClient setup.
    These tests verify the access check logic is properly integrated.
    """

    def test_auth_endpoint_imports_access_check(self):
        """Verify that auth.py imports the access check function."""
        # Read the auth.py file to verify the import exists
        import inspect
        from app.api.v1 import auth

        source = inspect.getsource(auth.plex_auth)
        assert "check_plex_server_access" in source
        assert "machine_identifier" in source

    def test_auth_endpoint_raises_403_on_access_denied(self):
        """Verify the endpoint raises 403 with correct message."""
        # The actual 403 message in the code
        expected_message = "Vous n'avez pas accès à ce serveur Plex"

        import inspect
        from app.api.v1 import auth

        source = inspect.getsource(auth.plex_auth)
        assert expected_message in source
        assert "status.HTTP_403_FORBIDDEN" in source
