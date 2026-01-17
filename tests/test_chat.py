"""Tests for chat completions endpoint."""

import os
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set API key before importing app
os.environ["DEDALUS_API_KEY"] = "test-api-key"


class MockMessage:
    """Mock message for testing."""

    def __init__(self, content: str, tool_calls: list[Any] | None = None) -> None:
        self.content = content
        self.role = "assistant"
        self.tool_calls = tool_calls


class MockDelta:
    """Mock delta for streaming tests."""

    def __init__(self, content: str, role: str | None = None) -> None:
        self.content = content
        self.role = role
        self.tool_calls = None


class MockChoice:
    """Mock choice for testing."""

    def __init__(self, content: str, finish_reason: str = "stop") -> None:
        self.message = MockMessage(content)
        self.delta = MockDelta(content)
        self.finish_reason = finish_reason


class MockUsage:
    """Mock usage for testing."""

    def __init__(self) -> None:
        self.prompt_tokens = 10
        self.completion_tokens = 5
        self.total_tokens = 15


class MockResponse:
    """Mock response for testing."""

    def __init__(
        self, content: str = "Test response", finish_reason: str = "stop"
    ) -> None:
        self.id = "chatcmpl-123"
        self.choices = [MockChoice(content, finish_reason)]
        self.usage = MockUsage()


def create_mock_global_client() -> MagicMock:
    """Create a mock global client."""
    mock_runner = MagicMock()
    mock_runner.create_completion = AsyncMock()
    mock_client = MagicMock()
    mock_client.runner = mock_runner
    mock_client.verify_connection = AsyncMock(return_value=True)
    return mock_client


@pytest.fixture
def mock_global_client() -> MagicMock:
    """Fixture for mock global client."""
    return create_mock_global_client()


@pytest.fixture
def mock_dedalus_runner(mock_global_client: MagicMock) -> MagicMock:
    """Fixture that patches the global client."""

    async def mock_create_completion(*args: Any, **kwargs: Any) -> Any:
        stream = kwargs.get("stream", False)

        if stream:

            async def stream_gen() -> AsyncGenerator[MockResponse, None]:
                # First chunk with role
                response = MockResponse("Hello ", "")
                response.choices[0].delta = MockDelta("Hello ", "assistant")
                response.choices[0].finish_reason = None
                yield response

                # Second chunk with content
                response2 = MockResponse("world!", "")
                response2.choices[0].delta = MockDelta("world!")
                response2.choices[0].finish_reason = None
                yield response2

                # Final chunk with finish_reason
                response3 = MockResponse("", "stop")
                response3.choices[0].delta = MockDelta("")
                response3.choices[0].finish_reason = "stop"
                yield response3

            return stream_gen()
        return MockResponse("Test response")

    mock_global_client.runner.create_completion = mock_create_completion
    return mock_global_client


@pytest_asyncio.fixture
async def async_client(
    mock_dedalus_runner: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing with mocked Dedalus client."""
    # Patch the global client
    from dedalus_labs_proxy.routes import chat, health
    from dedalus_labs_proxy.services import dedalus

    original_client = dedalus.global_client
    chat.global_client = mock_dedalus_runner
    health.global_client = mock_dedalus_runner

    from dedalus_labs_proxy.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    # Restore
    chat.global_client = original_client
    health.global_client = original_client


@pytest.mark.asyncio
async def test_chat_completions_non_streaming(async_client: AsyncClient) -> None:
    """Test non-streaming chat completion."""
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False,
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "id" in data
    assert data["object"] == "chat.completion"
    assert data["model"] == "openai/gpt-4"
    assert len(data["choices"]) > 0
    assert "message" in data["choices"][0]
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert "usage" in data


@pytest.mark.asyncio
async def test_chat_completions_with_temperature(async_client: AsyncClient) -> None:
    """Test chat completion with temperature parameter."""
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.7,
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_completions_with_max_tokens(async_client: AsyncClient) -> None:
    """Test chat completion with max_tokens parameter."""
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 100,
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_completions_with_top_p(async_client: AsyncClient) -> None:
    """Test chat completion with top_p parameter."""
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "top_p": 0.9,
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_completions_different_models(async_client: AsyncClient) -> None:
    """Test chat completion with different model names."""
    for model in [
        "openai/gpt-4",
        "openai/gpt-4o",
        "anthropic/claude-3-opus",
        "google/gemini-pro",
    ]:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Hello"}],
        }
        response = await async_client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        assert response.json()["model"] == model


@pytest.mark.asyncio
async def test_chat_completions_streaming(async_client: AsyncClient) -> None:
    """Test streaming chat completion."""
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    content = response.text
    assert "data: " in content
    assert "[DONE]" in content


@pytest.mark.asyncio
async def test_chat_completions_missing_messages(async_client: AsyncClient) -> None:
    """Test chat completion without messages field."""
    payload = {
        "model": "openai/gpt-4",
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_completions_missing_model(async_client: AsyncClient) -> None:
    """Test chat completion without model field."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_multiple_messages_in_chat_completions(
    async_client: AsyncClient,
) -> None:
    """Test chat completion with multiple messages."""
    payload = {
        "model": "openai/gpt-4",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ],
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_streaming_response_has_sse_headers(async_client: AsyncClient) -> None:
    """Test that streaming responses include proper SSE headers to prevent buffering."""
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200

    # Check for SSE-specific headers that prevent buffering
    assert (
        response.headers.get("cache-control") == "no-cache, no-store, must-revalidate"
    )
    assert response.headers.get("connection") == "keep-alive"
    assert response.headers.get("x-accel-buffering") == "no"


@pytest.mark.asyncio
async def test_iter_with_keepalive_sends_ping_on_timeout() -> None:
    """Test that _iter_with_keepalive yields None (ping signal) when stream is slow."""
    import asyncio

    from dedalus_labs_proxy.routes.chat import _iter_with_keepalive

    async def slow_stream() -> AsyncGenerator[str, None]:
        yield "first"
        await asyncio.sleep(0.3)  # Longer than keepalive interval
        yield "second"

    # Use a very short keepalive interval for testing
    results = []
    async for item in _iter_with_keepalive(slow_stream(), keepalive_interval=0.1):
        results.append(item)

    # Should have: "first", None (ping), None (ping), "second"
    # (at least one None ping during the 0.3s wait with 0.1s interval)
    assert "first" in results
    assert "second" in results
    assert None in results  # At least one keepalive ping was sent
