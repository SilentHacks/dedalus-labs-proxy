"""Tests for chat completions endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_chat_completions_non_streaming(async_client: AsyncClient) -> None:
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
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.7,
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_completions_with_max_tokens(async_client: AsyncClient) -> None:
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 100,
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_completions_with_top_p(async_client: AsyncClient) -> None:
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "top_p": 0.9,
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_completions_different_models(async_client: AsyncClient) -> None:
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
    payload = {"model": "openai/gpt-4"}
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_completions_missing_model(async_client: AsyncClient) -> None:
    payload = {"messages": [{"role": "user", "content": "Hello"}]}
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_multiple_messages_in_chat_completions(
    async_client: AsyncClient,
) -> None:
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
    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert (
        response.headers.get("cache-control") == "no-cache, no-store, must-revalidate"
    )
    assert response.headers.get("connection") == "keep-alive"
    assert response.headers.get("x-accel-buffering") == "no"
    assert response.headers.get("transfer-encoding") is None


@pytest.mark.asyncio
async def test_iter_with_keepalive_sends_ping_on_timeout() -> None:
    import asyncio
    from collections.abc import AsyncGenerator

    from dedalus_labs_proxy.services.completion.streaming_keepalive import (
        iter_with_keepalive,
    )

    async def slow_stream() -> AsyncGenerator[str, None]:
        yield "first"
        await asyncio.sleep(0.3)
        yield "second"

    results = []
    async for item in iter_with_keepalive(slow_stream(), keepalive_interval=0.1):
        results.append(item)

    assert "first" in results
    assert "second" in results
    assert None in results
