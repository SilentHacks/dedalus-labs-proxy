"""Tests for opt-in usage tracking."""

from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from dedalus_labs_proxy.config import init_config
from dedalus_labs_proxy.dependencies import get_dedalus_client
from dedalus_labs_proxy.main import app
from dedalus_labs_proxy.usage.estimator import estimate_context_tokens
from dedalus_labs_proxy.usage.store import UsageStore
from dedalus_labs_proxy.usage.tracker import parse_session_id
from tests.conftest import MockResponse, MockUsage

PROXY_KEY = "test-proxy-key"


@pytest.fixture
def usage_tracking_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Enable usage tracking for the duration of a test."""
    monkeypatch.setenv("USAGE_TRACKING", "true")
    monkeypatch.setenv("USAGE_HEADERS", "true")
    monkeypatch.setenv("USAGE_SSE_METADATA", "true")
    monkeypatch.delenv("USAGE_ADMIN_ENABLED", raising=False)
    init_config(require_api_key=True)
    yield
    monkeypatch.delenv("USAGE_TRACKING", raising=False)
    monkeypatch.delenv("USAGE_HEADERS", raising=False)
    monkeypatch.delenv("USAGE_SSE_METADATA", raising=False)
    init_config(require_api_key=True)


@pytest.fixture
def usage_admin_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Enable usage tracking and admin routes."""
    monkeypatch.setenv("USAGE_TRACKING", "true")
    monkeypatch.setenv("USAGE_ADMIN_ENABLED", "true")
    monkeypatch.setenv("PROXY_API_KEYS", PROXY_KEY)
    init_config(require_api_key=True)
    yield
    monkeypatch.delenv("USAGE_TRACKING", raising=False)
    monkeypatch.delenv("USAGE_ADMIN_ENABLED", raising=False)
    monkeypatch.delenv("PROXY_API_KEYS", raising=False)
    init_config(require_api_key=True)


@pytest_asyncio.fixture
async def tracking_client(
    usage_tracking_enabled: None,
) -> AsyncGenerator[AsyncClient, None]:
    from tests.conftest import create_mock_dedalus_client

    client = create_mock_dedalus_client()
    app.dependency_overrides[get_dedalus_client] = lambda: client
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        http_client._mock_dedalus_client = client  # type: ignore[attr-defined]
        yield http_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(
    usage_admin_enabled: None,
) -> AsyncGenerator[AsyncClient, None]:
    from tests.conftest import create_mock_dedalus_client

    client = create_mock_dedalus_client()
    app.dependency_overrides[get_dedalus_client] = lambda: client
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_no_usage_headers_when_disabled(async_client: AsyncClient) -> None:
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert "X-Proxy-Request-Id" not in response.headers


def test_estimate_context_tokens_counts_messages_and_tools() -> None:
    messages = [{"role": "user", "content": "Hello world"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "demo",
                "description": "Demo tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    estimate = estimate_context_tokens(messages, tools, chars_per_token=4)
    assert estimate > 0


def test_parse_session_id_accepts_valid_values() -> None:
    assert parse_session_id("opencode-run-abc_123") == "opencode-run-abc_123"


def test_parse_session_id_rejects_invalid_values() -> None:
    assert parse_session_id("bad session id") is None
    assert parse_session_id("x" * 129) is None


@pytest.mark.asyncio
async def test_non_streaming_records_usage_headers(tracking_client: AsyncClient) -> None:
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    response = await tracking_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert response.headers.get("X-Proxy-Total-Tokens") == "15"
    assert response.headers.get("X-Proxy-Context-Estimate") is not None


@pytest.mark.asyncio
async def test_streaming_absorbs_usage_chunk(
    tracking_client: AsyncClient,
) -> None:
    mock_dedalus_client = tracking_client._mock_dedalus_client  # type: ignore[attr-defined]
    async def mock_create_completion(*args: Any, **kwargs: Any) -> Any:
        assert kwargs.get("stream_options") == {"include_usage": True}

        async def stream_gen() -> AsyncGenerator[MockResponse, None]:
            response = MockResponse("Hello ", "")
            response.choices[0].delta.content = "Hello "
            response.choices[0].finish_reason = None
            yield response

            usage_response = MockResponse("", "stop")
            usage_response.choices = []
            usage_response.usage = MockUsage()
            yield usage_response

        return stream_gen()

    mock_dedalus_client.runner.create_completion = mock_create_completion

    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
    }
    response = await tracking_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert '"usage"' not in response.text
    assert "x-proxy-usage" in response.text


@pytest.mark.asyncio
async def test_streaming_forwards_usage_chunk_when_requested(
    tracking_client: AsyncClient,
) -> None:
    mock_dedalus_client = tracking_client._mock_dedalus_client  # type: ignore[attr-defined]
    async def mock_create_completion(*args: Any, **kwargs: Any) -> Any:
        async def stream_gen() -> AsyncGenerator[MockResponse, None]:
            usage_response = MockResponse("", "stop")
            usage_response.choices = []
            usage_response.usage = MockUsage()
            yield usage_response

        return stream_gen()

    mock_dedalus_client.runner.create_completion = mock_create_completion

    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    response = await tracking_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert '"usage"' in response.text


@pytest.mark.asyncio
async def test_session_aggregation(tracking_client: AsyncClient) -> None:
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    headers = {"X-Proxy-Session-Id": "session-abc"}

    first = await tracking_client.post("/v1/chat/completions", json=payload, headers=headers)
    second = await tracking_client.post("/v1/chat/completions", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers.get("X-Proxy-Session-Total-Tokens") == "15"
    assert second.headers.get("X-Proxy-Session-Total-Tokens") == "30"


@pytest.mark.asyncio
async def test_invalid_session_id_is_ignored(tracking_client: AsyncClient) -> None:
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    response = await tracking_client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"X-Proxy-Session-Id": "bad session"},
    )
    assert response.status_code == 200
    assert "X-Proxy-Session-Id" not in response.headers


@pytest.mark.asyncio
async def test_admin_usage_requires_auth(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/v1/admin/usage")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_usage_returns_summary(admin_client: AsyncClient) -> None:
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    await admin_client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {PROXY_KEY}"},
    )

    response = await admin_client.get(
        "/v1/admin/usage",
        headers={"Authorization": f"Bearer {PROXY_KEY}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] >= 1
    assert "openai/gpt-4" in data["by_model"]


@pytest.mark.asyncio
async def test_admin_session_lookup(admin_client: AsyncClient) -> None:
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    headers = {
        "Authorization": f"Bearer {PROXY_KEY}",
        "X-Proxy-Session-Id": "admin-session",
    }
    await admin_client.post("/v1/chat/completions", json=payload, headers=headers)

    response = await admin_client.get(
        "/v1/admin/sessions/admin-session",
        headers={"Authorization": f"Bearer {PROXY_KEY}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session"]["session_id"] == "admin-session"
    assert data["session"]["request_count"] == 1


@pytest.mark.asyncio
async def test_usage_store_summary() -> None:
    store = UsageStore(max_records=10)
    from dedalus_labs_proxy.usage.models import UsageRecord

    record = UsageRecord(
        request_id="req-1",
        timestamp=1.0,
        model="openai/gpt-4",
        stream=False,
        message_count=1,
        tool_count=0,
        context_estimate_tokens=10,
        context_window_tokens=128000,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        finish_reason="stop",
        latency_ms=100.0,
        client_key_hash="abc123",
        session_id="session-1",
        error=False,
    )
    await store.record(record)
    summary = await store.get_summary()
    assert summary.total_requests == 1
    assert summary.total_tokens == 15
