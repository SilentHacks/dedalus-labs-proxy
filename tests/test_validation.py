"""Tests for validation error handling."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_validation_error_missing_model(async_client: AsyncClient) -> None:
    payload = {"messages": [{"role": "user", "content": "Hello"}]}
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422

    data = response.json()
    assert "error" in data
    assert data["error"]["type"] == "validation_error"
    assert "details" in data["error"]


@pytest.mark.asyncio
async def test_validation_error_missing_messages(async_client: AsyncClient) -> None:
    payload = {"model": "gpt-4"}
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422

    data = response.json()
    assert "error" in data
    assert data["error"]["type"] == "validation_error"


@pytest.mark.asyncio
async def test_validation_error_invalid_messages_format(
    async_client: AsyncClient,
) -> None:
    payload = {"model": "gpt-4", "messages": "not an array"}
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422

    data = response.json()
    assert "error" in data
    assert data["error"]["type"] == "validation_error"


@pytest.mark.asyncio
async def test_validation_error_empty_messages(async_client: AsyncClient) -> None:
    payload = {"model": "gpt-4", "messages": []}
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code in [200, 400, 401, 422]


@pytest.mark.asyncio
async def test_validation_error_missing_role_in_message(
    async_client: AsyncClient,
) -> None:
    payload = {"model": "gpt-4", "messages": [{"content": "Hello"}]}
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_error_invalid_temperature(async_client: AsyncClient) -> None:
    payload = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": "hot",
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422
