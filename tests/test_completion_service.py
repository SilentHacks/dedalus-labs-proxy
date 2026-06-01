"""Tests for tool_choice serialization and Google streaming prep."""

from unittest.mock import AsyncMock, MagicMock

import dedalus_labs
import pytest
from httpx import AsyncClient

from dedalus_labs_proxy.services.completion.service import serialize_tool_choice


def test_serialize_tool_choice_passthrough_unknown_string() -> None:
    assert serialize_tool_choice("custom-mode") == "custom-mode"


def test_serialize_tool_choice_auto_is_none() -> None:
    assert serialize_tool_choice("auto") is None


@pytest.mark.asyncio
async def test_google_stream_injects_thought_signatures_without_tools_field(
    async_client: AsyncClient,
    mock_dedalus_client: MagicMock,
) -> None:
    captured: dict[str, object] = {}

    async def mock_create_completion(*args: object, **kwargs: object) -> MagicMock:
        captured.update(kwargs)

        class Response:
            choices = [
                MagicMock(
                    message=MagicMock(content="ok", tool_calls=None, role="assistant"),
                    finish_reason="stop",
                )
            ]

        return Response()

    mock_dedalus_client.runner.create_completion = mock_create_completion

    payload = {
        "model": "google/gemini-3-pro-preview",
        "stream": True,
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "demo", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "{}"},
            {"role": "user", "content": "continue"},
        ],
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    messages = captured["messages"]
    assert messages[0]["tool_calls"][0]["thought_signature"] is not None


@pytest.mark.asyncio
async def test_streaming_auth_error_emits_done(
    async_client: AsyncClient,
    mock_dedalus_client: MagicMock,
) -> None:
    async def raise_auth(*args: object, **kwargs: object) -> None:
        raise dedalus_labs.AuthenticationError("bad key")

    mock_dedalus_client.runner.create_completion = raise_auth

    payload = {
        "model": "openai/gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
    }
    response = await async_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert "Authentication failed" in response.text
    assert "[DONE]" in response.text
