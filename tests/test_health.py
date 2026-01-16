"""Tests for health endpoint."""

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
async def test_health_check(async_client: AsyncClient) -> None:
    """Test the /health endpoint returns OK status."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_check_response_time(async_client: AsyncClient) -> None:
    """Test the /health endpoint responds quickly."""
    import time

    start = time.time()
    response = await async_client.get("/health")
    elapsed_ms = (time.time() - start) * 1000

    assert response.status_code == 200
    assert elapsed_ms < 100  # Should be much faster than 10ms in practice
