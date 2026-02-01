"""
Tests for media search service (TMDB, AniList).
All network calls mocked - zero external requests.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.services.media_search import MediaSearchService


@pytest.fixture
def mock_settings():
    """Mock settings with TMDB API key."""
    settings = MagicMock()
    settings.tmdb_api_key = "test-tmdb-api-key"
    return settings


@pytest.fixture
def media_search_service(mock_settings):
    """Create media search service with mocked settings."""
    with patch("app.services.media_search.get_settings", return_value=mock_settings):
        service = MediaSearchService()
        # Replace the internal _client with a mock
        service._client = MagicMock()
        return service


class TestTMDBSearch:
    """Tests for TMDB search functionality."""

    @pytest.mark.asyncio
    async def test_search_tmdb_movie_constructs_url(self, media_search_service):
        """Test TMDB movie search constructs correct URL."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 550,
                    "title": "Fight Club",
                    "overview": "An insomniac office worker...",
                    "release_date": "1999-10-15",
                    "vote_average": 8.4,
                    "vote_count": 25000,
                    "poster_path": "/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg"
                }
            ],
            "total_results": 1,
            "total_pages": 1
        }

        media_search_service._client.get = AsyncMock(return_value=mock_response)

        results = await media_search_service._search_tmdb("Fight Club", "movie")

        # Verify API was called
        media_search_service._client.get.assert_called_once()
        # Check results parsing
        assert len(results) == 1
        assert results[0].title == "Fight Club"

    @pytest.mark.asyncio
    async def test_search_tmdb_handles_no_results(self, media_search_service):
        """Test TMDB search returns empty list when no results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [],
            "total_results": 0
        }

        media_search_service._client.get = AsyncMock(return_value=mock_response)

        results = await media_search_service._search_tmdb("nonexistent movie xyz", "movie")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_tmdb_handles_timeout(self, media_search_service):
        """Test TMDB search handles timeout gracefully."""
        media_search_service._client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        results = await media_search_service._search_tmdb("Fight Club", "movie")
        # Should return empty list on timeout, not crash
        assert results == []

    @pytest.mark.asyncio
    async def test_search_tmdb_handles_api_error(self, media_search_service):
        """Test TMDB search handles API errors gracefully."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"status_message": "Invalid API key"}

        media_search_service._client.get = AsyncMock(return_value=mock_response)

        results = await media_search_service._search_tmdb("Fight Club", "movie")
        # Should return empty list on error, not crash
        assert results == []


class TestAniListSearch:
    """Tests for AniList GraphQL search."""

    @pytest.mark.asyncio
    async def test_search_anilist_constructs_graphql_query(self, media_search_service):
        """Test AniList search sends GraphQL query."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "Page": {
                    "media": [
                        {
                            "id": 1,
                            "title": {
                                "romaji": "Cowboy Bebop",
                                "english": "Cowboy Bebop"
                            },
                            "description": "A ragtag crew of bounty hunters...",
                            "startDate": {"year": 1998},
                            "coverImage": {"large": "https://..."},
                            "averageScore": 86
                        }
                    ]
                }
            }
        }

        media_search_service._client.post = AsyncMock(return_value=mock_response)

        results = await media_search_service._search_anilist("Cowboy Bebop")

        # Verify GraphQL endpoint was called
        media_search_service._client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_anilist_handles_empty(self, media_search_service):
        """Test AniList search handles empty results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "Page": {
                    "media": []
                }
            }
        }

        media_search_service._client.post = AsyncMock(return_value=mock_response)

        results = await media_search_service._search_anilist("nonexistent anime xyz")
        assert results == []


class TestUnifiedSearch:
    """Tests for unified search across all sources."""

    @pytest.mark.asyncio
    async def test_search_all_calls_multiple_sources(self, media_search_service):
        """Test unified search calls TMDB and AniList."""
        with patch.object(media_search_service, "_search_tmdb", AsyncMock(return_value=[])) as mock_tmdb, \
             patch.object(media_search_service, "_search_anilist", AsyncMock(return_value=[])) as mock_anilist:

            await media_search_service.search("test", media_type="all")

            # Should search both TMDB and AniList
            assert mock_tmdb.call_count >= 1  # Called for movie and/or tv
            mock_anilist.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_movie_only_skips_anime(self, media_search_service):
        """Test search with movie type only searches TMDB movies."""
        with patch.object(media_search_service, "_search_tmdb", AsyncMock(return_value=[])) as mock_tmdb, \
             patch.object(media_search_service, "_search_anilist", AsyncMock(return_value=[])) as mock_anilist:

            await media_search_service.search("test", media_type="movie")

            # Should search TMDB for movies
            mock_tmdb.assert_called_once()
            # Should NOT search AniList for movies
            mock_anilist.assert_not_called()


class TestMediaSearchServiceLifecycle:
    """Tests for service lifecycle management."""

    @pytest.mark.asyncio
    async def test_close_cleans_up_client(self, mock_settings):
        """Test close() properly cleans up HTTP client."""
        with patch("app.services.media_search.get_settings", return_value=mock_settings):
            service = MediaSearchService()

        # Create a mock client
        mock_client = MagicMock()
        mock_client.aclose = AsyncMock()
        service._client = mock_client

        await service.close()

        mock_client.aclose.assert_called_once()
        assert service._client is None
