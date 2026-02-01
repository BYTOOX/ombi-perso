"""
Tests for downloader service (qBittorrent).
All network calls mocked - zero external requests.
"""
import pytest
from unittest.mock import MagicMock, patch
import qbittorrentapi

from app.services.downloader import DownloaderService


@pytest.fixture
def mock_settings():
    """Mock settings with qBittorrent configuration."""
    settings = MagicMock()
    settings.qbittorrent_url = "http://localhost:8080"
    settings.qbittorrent_username = "admin"
    settings.qbittorrent_password = "adminpassword"
    settings.download_path = "/downloads"
    return settings


@pytest.fixture
def downloader_service(mock_settings):
    """Create downloader service with mocked settings."""
    with patch("app.services.downloader.get_settings", return_value=mock_settings):
        return DownloaderService()


class TestDownloaderConfiguration:
    """Tests for qBittorrent configuration validation."""

    def test_is_configured_with_valid_url(self, mock_settings):
        """Test configuration check with valid URL."""
        with patch("app.services.downloader.get_settings", return_value=mock_settings):
            service = DownloaderService()
            assert service._is_configured() is True

    def test_is_not_configured_with_empty_url(self, mock_settings):
        """Test configuration check with empty URL."""
        mock_settings.qbittorrent_url = ""
        with patch("app.services.downloader.get_settings", return_value=mock_settings):
            service = DownloaderService()
            assert service._is_configured() is False

    def test_is_not_configured_with_placeholder_url(self, mock_settings):
        """Test configuration check with placeholder URL."""
        mock_settings.qbittorrent_url = "http://your-qbittorrent-host:8080"
        with patch("app.services.downloader.get_settings", return_value=mock_settings):
            service = DownloaderService()
            assert service._is_configured() is False

    def test_is_configured_with_localhost(self, mock_settings):
        """Test localhost is considered valid configuration."""
        mock_settings.qbittorrent_url = "http://localhost:8080"
        with patch("app.services.downloader.get_settings", return_value=mock_settings):
            service = DownloaderService()
            assert service._is_configured() is True


class TestDownloaderConnection:
    """Tests for qBittorrent connection handling."""

    def test_client_returns_none_when_not_configured(self, mock_settings):
        """Test client property returns None when not configured."""
        mock_settings.qbittorrent_url = ""
        with patch("app.services.downloader.get_settings", return_value=mock_settings):
            service = DownloaderService()
            assert service.client is None

    def test_client_connection_failure_caching(self, downloader_service):
        """Test connection failures are cached to avoid repeated attempts."""
        # Simulate connection failure
        downloader_service._connection_failed = True

        # Should return None without attempting connection
        assert downloader_service.client is None

    def test_client_handles_connection_error(self, downloader_service):
        """Test client handles connection errors gracefully."""
        with patch("qbittorrentapi.Client", side_effect=Exception("Connection failed")):
            client = downloader_service.client

            # Should not crash, just return None
            assert client is None
            # Should cache the failure
            assert downloader_service._connection_failed is True


class TestTorrentOperations:
    """Tests for torrent operations."""

    def test_add_torrent_returns_false_when_not_connected(self, downloader_service):
        """Test add_torrent returns False when not connected."""
        downloader_service._client = None
        downloader_service._connection_failed = True

        result = downloader_service.add_torrent(
            torrent_url="https://example.com/test.torrent"
        )

        assert result is False or result is None

    def test_get_all_torrents_returns_empty_when_not_connected(self, downloader_service):
        """Test get_all_torrents returns empty list when not connected."""
        downloader_service._client = None
        downloader_service._connection_failed = True

        torrents = downloader_service.get_all_torrents()

        assert torrents == []

    def test_get_all_torrents_with_client(self, downloader_service):
        """Test get_all_torrents calls client when connected."""
        mock_qb_client = MagicMock()
        mock_qb_client.torrents_info.return_value = [
            MagicMock(
                hash="abc123",
                name="Test Movie 2024",
                progress=0.5,
                state="downloading"
            )
        ]

        downloader_service._client = mock_qb_client

        torrents = downloader_service.get_all_torrents()

        mock_qb_client.torrents_info.assert_called_once()
        assert len(torrents) == 1


class TestHealthCheck:
    """Tests for service health check."""

    def test_health_check_connected(self, downloader_service):
        """Test health check when connected."""
        mock_qb_client = MagicMock()
        mock_qb_client.app.version = "4.5.0"
        mock_qb_client.app.web_api_version = "2.8.0"

        downloader_service._client = mock_qb_client

        health = downloader_service.health_check()

        assert health["status"] == "ok"
        assert "version" in health

    def test_health_check_not_connected(self, downloader_service):
        """Test health check when not connected."""
        downloader_service._client = None
        downloader_service._connection_failed = True

        health = downloader_service.health_check()

        # When not connected, should return error status
        assert health["status"] in ["error", "not_configured"]


class TestDownloaderServiceInitialization:
    """Tests for service initialization."""

    def test_service_initializes_without_error(self, mock_settings):
        """Test service can be created."""
        with patch("app.services.downloader.get_settings", return_value=mock_settings):
            service = DownloaderService()
            assert service is not None
            assert service._client is None
            assert service._connection_failed is False

    def test_service_stores_settings(self, mock_settings):
        """Test service stores settings reference."""
        with patch("app.services.downloader.get_settings", return_value=mock_settings):
            service = DownloaderService()
            assert service.settings == mock_settings
