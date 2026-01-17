"""Tests for models endpoint."""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set API key before importing app
os.environ["DEDALUS_API_KEY"] = "test-api-key"

from dedalus_labs_proxy.main import app


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_models_endpoint(async_client: AsyncClient) -> None:
    """Test the /v1/models endpoint returns empty list.

    The proxy no longer maintains a model mapping - users should pass
    model names directly as expected by the Dedalus Labs API.
    """
    response = await async_client.get("/v1/models")
    assert response.status_code == 200

    data = response.json()
    assert data["object"] == "list"
    assert "data" in data
    assert len(data["data"]) == 0
