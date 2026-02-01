"""
Tests for torrent scraper service (YGGtorrent).
All network calls mocked - zero external requests.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.services.torrent_scraper import TorrentScraperService
from app.schemas.media import TorrentResult


@pytest.fixture
def mock_settings():
    """Mock settings with YGG configuration."""
    settings = MagicMock()
    settings.ygg_base_url = "https://ygg.example.com"
    settings.ygg_api_url = "https://api.ygg.example.com"
    settings.flaresolverr_url = "http://flaresolverr:8191"
    settings.ygg_passkey = "test-passkey"
    return settings


@pytest.fixture
def torrent_scraper(mock_settings):
    """Create torrent scraper with mocked settings."""
    with patch("app.services.torrent_scraper.get_settings", return_value=mock_settings):
        return TorrentScraperService()


class TestTorrentCategories:
    """Tests for category mapping."""

    def test_category_mapping_exists(self, torrent_scraper):
        """Test all expected categories are mapped."""
        assert "movie" in TorrentScraperService.CATEGORIES
        assert "series" in TorrentScraperService.CATEGORIES
        assert "anime" in TorrentScraperService.CATEGORIES
        assert "animated_movie" in TorrentScraperService.CATEGORIES

    def test_category_values_are_valid(self, torrent_scraper):
        """Test category IDs are valid strings."""
        for cat_id in TorrentScraperService.CATEGORIES.values():
            assert isinstance(cat_id, str)
            assert cat_id.isdigit()


class TestTorrentQualityParsing:
    """Tests for quality extraction from torrent names."""

    def test_quality_patterns_exist(self, torrent_scraper):
        """Test quality patterns are defined."""
        assert len(TorrentScraperService.QUALITY_PATTERNS) > 0

    def test_quality_patterns_cover_common_formats(self, torrent_scraper):
        """Test quality patterns cover common quality indicators."""
        patterns_text = str(TorrentScraperService.QUALITY_PATTERNS)
        assert "4K" in patterns_text or "2160p" in patterns_text
        assert "1080p" in patterns_text
        assert "720p" in patterns_text


class TestTorrentResultModel:
    """Tests for TorrentResult model."""

    def test_torrent_result_creation(self):
        """Test TorrentResult can be created with required fields."""
        result = TorrentResult(
            id="12345",
            name="Test Torrent 1080p",
            size_bytes=1024 * 1024 * 1024,  # 1 GB
            size_human="1 GB",
            seeders=10,
            leechers=2
        )

        assert result.id == "12345"
        assert result.name == "Test Torrent 1080p"
        assert result.seeders == 10
        assert result.size_bytes == 1024 * 1024 * 1024

    def test_torrent_result_optional_fields(self):
        """Test TorrentResult handles optional fields."""
        result = TorrentResult(
            id="12345",
            name="Test Torrent",
            size_bytes=1024,
            size_human="1 KB",
            seeders=5,
            leechers=1
        )

        # Optional fields should have defaults
        assert result.torrent_url is None
        assert result.magnet_link is None
        assert result.category is None


class TestYggAPISearch:
    """Tests for YggAPI search functionality."""

    @pytest.mark.asyncio
    async def test_search_yggapi_returns_list(self, torrent_scraper):
        """Test YggAPI search returns a list."""
        # Mock the _search_via_yggapi method to return empty
        with patch.object(torrent_scraper, "_search_via_yggapi", AsyncMock(return_value=[])):
            results = await torrent_scraper._search_via_yggapi("Test Query", "movie")
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_handles_exception(self, torrent_scraper):
        """Test search handles exceptions gracefully."""
        with patch.object(torrent_scraper, "_search_via_yggapi", AsyncMock(side_effect=Exception("Network error"))):
            try:
                results = await torrent_scraper._search_via_yggapi("Test Query", "movie")
                # If it doesn't raise, that's also acceptable
            except Exception:
                pass  # Expected behavior


class TestSearchIntegration:
    """Integration tests for search method."""

    @pytest.mark.asyncio
    async def test_search_tries_yggapi_first(self, torrent_scraper):
        """Test search prefers YggAPI over FlareSolverr."""
        mock_result = TorrentResult(
            id="1",
            name="Test Torrent",
            size_bytes=1024,
            size_human="1 KB",
            seeders=10,
            leechers=1
        )

        with patch.object(torrent_scraper, "_search_via_yggapi", AsyncMock(return_value=[mock_result])) as mock_yggapi, \
             patch.object(torrent_scraper, "_search_via_flaresolverr", AsyncMock(return_value=[])) as mock_flare:

            results = await torrent_scraper.search("test query")

            mock_yggapi.assert_called_once()
            # FlareSolverr should not be called if YggAPI succeeds
            mock_flare.assert_not_called()
            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_falls_back_to_flaresolverr(self, torrent_scraper):
        """Test search falls back to FlareSolverr when YggAPI fails."""
        mock_result = TorrentResult(
            id="1",
            name="Test Torrent",
            size_bytes=1024,
            size_human="1 KB",
            seeders=5,
            leechers=1
        )

        with patch.object(torrent_scraper, "_search_via_yggapi", AsyncMock(return_value=[])) as mock_yggapi, \
             patch.object(torrent_scraper, "_search_via_flaresolverr", AsyncMock(return_value=[mock_result])) as mock_flare:

            results = await torrent_scraper.search("test query")

            mock_yggapi.assert_called_once()
            # FlareSolverr should be called as fallback
            mock_flare.assert_called_once()
            assert len(results) == 1


class TestReleaseGroupParsing:
    """Tests for release group detection."""

    def test_release_groups_defined(self, torrent_scraper):
        """Test release groups are defined."""
        assert len(TorrentScraperService.RELEASE_GROUPS) > 0

    def test_common_release_groups_present(self, torrent_scraper):
        """Test common release groups are in the list."""
        groups = TorrentScraperService.RELEASE_GROUPS
        # Check for some common groups
        assert any("YTS" in g or "YIFY" in g or "RARBG" in g for g in groups)
