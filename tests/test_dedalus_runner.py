"""Tests for DedalusRunner token parameter handling."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dedalus_labs_proxy.services.dedalus import DedalusRunner, build_completion_kwargs


@pytest.mark.asyncio
async def test_openai_model_uses_max_completion_tokens_only() -> None:
    sdk_client = MagicMock()
    sdk_client.chat.completions.create = AsyncMock(return_value="ok")
    runner = DedalusRunner(sdk_client, tool_max_tokens=128000)

    await runner.create_completion(
        model="openai/gpt-4",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
    )

    kwargs = sdk_client.chat.completions.create.await_args.kwargs
    assert kwargs["max_completion_tokens"] == 100
    assert "max_tokens" not in kwargs


@pytest.mark.asyncio
async def test_non_openai_model_uses_max_tokens_only() -> None:
    sdk_client = MagicMock()
    sdk_client.chat.completions.create = AsyncMock(return_value="ok")
    runner = DedalusRunner(sdk_client, tool_max_tokens=128000)

    await runner.create_completion(
        model="anthropic/claude-3-opus",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
    )

    kwargs = sdk_client.chat.completions.create.await_args.kwargs
    assert kwargs["max_tokens"] == 100
    assert "max_completion_tokens" not in kwargs


@pytest.mark.asyncio
async def test_tool_request_uses_tool_max_tokens_when_unset() -> None:
    sdk_client = MagicMock()
    sdk_client.chat.completions.create = AsyncMock(return_value="ok")
    runner = DedalusRunner(sdk_client, tool_max_tokens=64000)

    await runner.create_completion(
        model="anthropic/claude-3-opus",
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "demo", "parameters": {}}}],
    )

    kwargs = sdk_client.chat.completions.create.await_args.kwargs
    assert kwargs["max_tokens"] == 64000


def test_build_completion_kwargs_openai_uses_max_completion_tokens() -> None:
    kwargs = build_completion_kwargs(
        model="openai/gpt-4",
        messages=[{"role": "user", "content": "hi"}],
        stream=False,
        tool_max_tokens=128000,
        max_tokens=50,
    )
    assert kwargs["max_completion_tokens"] == 50
    assert "max_tokens" not in kwargs


def test_build_completion_kwargs_anthropic_uses_max_tokens_only() -> None:
    kwargs = build_completion_kwargs(
        model="anthropic/claude-3-opus",
        messages=[{"role": "user", "content": "hi"}],
        stream=False,
        tool_max_tokens=128000,
        max_tokens=50,
    )
    assert kwargs["max_tokens"] == 50
    assert "max_completion_tokens" not in kwargs
