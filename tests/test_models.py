"""Tests for models endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_models_endpoint(async_client: AsyncClient) -> None:
    response = await async_client.get("/v1/models")
    assert response.status_code == 200

    data = response.json()
    assert data["object"] == "list"
    assert "data" in data
    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == "openai/gpt-4"
