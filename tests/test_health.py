"""Tests for health endpoint."""

from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient) -> None:
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_check_response_time(async_client: AsyncClient) -> None:
    import time

    start = time.time()
    response = await async_client.get("/health")
    elapsed_ms = (time.time() - start) * 1000

    assert response.status_code == 200
    assert elapsed_ms < 100


@pytest.mark.asyncio
async def test_dedalus_health_check(
    async_client: AsyncClient, mock_dedalus_client: MagicMock
) -> None:
    response = await async_client.get("/health/dedalus")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    mock_dedalus_client.verify_connection.assert_awaited_once()
