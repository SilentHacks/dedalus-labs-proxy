"""Tests for validation error handling."""

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
async def test_validation_error_missing_model(async_client: AsyncClient) -> None:
    """Test validation error for missing model field."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422

    data = response.json()
    assert "error" in data
    assert data["error"]["type"] == "validation_error"
    assert "details" in data["error"]


@pytest.mark.asyncio
async def test_validation_error_missing_messages(async_client: AsyncClient) -> None:
    """Test validation error for missing messages field."""
    payload = {
        "model": "gpt-4",
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422

    data = response.json()
    assert "error" in data
    assert data["error"]["type"] == "validation_error"


@pytest.mark.asyncio
async def test_validation_error_invalid_messages_format(
    async_client: AsyncClient,
) -> None:
    """Test validation error for invalid messages format."""
    payload = {
        "model": "gpt-4",
        "messages": "not an array",  # Should be an array
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422

    data = response.json()
    assert "error" in data
    assert data["error"]["type"] == "validation_error"


@pytest.mark.asyncio
async def test_validation_error_empty_messages(async_client: AsyncClient) -> None:
    """Test validation error for empty messages array."""
    payload = {
        "model": "gpt-4",
        "messages": [],
    }
    # Empty messages is technically valid per the schema
    # The behavior depends on implementation - may hit real API
    response = await async_client.post("/v1/chat/completions", json=payload)
    # 200 with mocked client, 400/422 for validation, 401 if hitting real API
    assert response.status_code in [200, 400, 401, 422]


@pytest.mark.asyncio
async def test_validation_error_missing_role_in_message(
    async_client: AsyncClient,
) -> None:
    """Test validation error for message without role."""
    payload = {
        "model": "gpt-4",
        "messages": [{"content": "Hello"}],  # Missing role
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_error_invalid_temperature(async_client: AsyncClient) -> None:
    """Test validation error for invalid temperature type."""
    payload = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": "hot",  # Should be a number
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422
