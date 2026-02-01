"""
Tests for health check endpoint.

Smoke tests to verify the application is running correctly.
"""
import pytest
from httpx import AsyncClient


class TestHealthCheck:
    """Tests for GET /api/health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client: AsyncClient):
        """Health endpoint returns 200 with status ok."""
        response = await client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "app" in data

    @pytest.mark.asyncio
    async def test_health_no_auth_required(self, client: AsyncClient):
        """Health endpoint is accessible without authentication."""
        # No Authorization header provided
        response = await client.get("/api/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_app_name(self, client: AsyncClient):
        """Health endpoint returns application name."""
        response = await client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert "app" in data
        assert isinstance(data["app"], str)
        assert len(data["app"]) > 0
