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
    """Test the /v1/models endpoint returns list of models."""
    response = await async_client.get("/v1/models")
    assert response.status_code == 200

    data = response.json()
    assert data["object"] == "list"
    assert "data" in data
    assert len(data["data"]) > 0

    for model in data["data"]:
        assert "id" in model
        assert model["object"] == "model"
        assert model["owned_by"] == "dedalus"


@pytest.mark.asyncio
async def test_models_endpoint_contains_expected_models(
    async_client: AsyncClient,
) -> None:
    """Test that expected models are in the list."""
    response = await async_client.get("/v1/models")
    data = response.json()
    model_ids = [model["id"] for model in data["data"]]

    assert "gpt-4" in model_ids
    assert "gpt-4o" in model_ids
    assert "claude-3-opus" in model_ids
    assert "gemini-pro" in model_ids
