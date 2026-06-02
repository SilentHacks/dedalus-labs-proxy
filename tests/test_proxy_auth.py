"""Tests for optional client API key authentication."""

import os
from collections.abc import Generator

import pytest
from httpx import AsyncClient

from dedalus_labs_proxy.auth import extract_bearer_token
from dedalus_labs_proxy.config import init_config

PROXY_KEY = "test-proxy-key"


@pytest.fixture
def proxy_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Enable proxy auth for the duration of a test."""
    original = os.environ.get("PROXY_API_KEYS")
    monkeypatch.setenv("PROXY_API_KEYS", PROXY_KEY)
    init_config(require_api_key=True)
    yield
    if original is None:
        monkeypatch.delenv("PROXY_API_KEYS", raising=False)
    else:
        monkeypatch.setenv("PROXY_API_KEYS", original)
    init_config(require_api_key=True)


def test_extract_bearer_token_valid() -> None:
    assert extract_bearer_token("Bearer my-token") == "my-token"


def test_extract_bearer_token_case_insensitive_scheme() -> None:
    assert extract_bearer_token("bearer my-token") == "my-token"


def test_extract_bearer_token_rejects_basic() -> None:
    assert extract_bearer_token("Basic dXNlcjpwYXNz") is None


def test_extract_bearer_token_rejects_missing() -> None:
    assert extract_bearer_token(None) is None
    assert extract_bearer_token("") is None


def test_extract_bearer_token_rejects_empty_credentials() -> None:
    assert extract_bearer_token("Bearer ") is None
    assert extract_bearer_token("Bearer") is None


@pytest.mark.asyncio
async def test_no_proxy_auth_allows_unauthenticated(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get("/v1/models")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_missing_auth_returns_401(
    async_client: AsyncClient, proxy_auth_enabled: None
) -> None:
    response = await async_client.get("/v1/models")
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["type"] == "authentication_error"
    assert "didn't provide an API key" in data["error"]["message"]


@pytest.mark.asyncio
async def test_invalid_auth_returns_401(
    async_client: AsyncClient, proxy_auth_enabled: None
) -> None:
    response = await async_client.get(
        "/v1/models",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["type"] == "authentication_error"
    assert data["error"]["message"] == "Incorrect API key provided."


@pytest.mark.asyncio
async def test_valid_auth_allows_models(
    async_client: AsyncClient, proxy_auth_enabled: None
) -> None:
    response = await async_client.get(
        "/v1/models",
        headers={"Authorization": f"Bearer {PROXY_KEY}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_valid_auth_allows_chat_completions(
    async_client: AsyncClient, proxy_auth_enabled: None
) -> None:
    response = await async_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {PROXY_KEY}"},
        json={
            "model": "openai/gpt-4",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_exempt_without_auth(
    async_client: AsyncClient, proxy_auth_enabled: None
) -> None:
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_dedalus_health_requires_auth(
    async_client: AsyncClient, proxy_auth_enabled: None
) -> None:
    response = await async_client.get("/health/dedalus")
    assert response.status_code == 401
