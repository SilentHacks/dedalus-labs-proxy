"""Dedalus SDK wrapper service."""

import logging
from collections.abc import AsyncGenerator
from typing import Any, Literal, overload

from dedalus_labs import AsyncDedalus

from dedalus_labs_proxy.config import get_config

logger = logging.getLogger("dedalus-proxy")


def _apply_token_limits(
    kwargs: dict[str, Any],
    *,
    model: str,
    max_tokens: int | None,
    max_completion_tokens: int | None,
    tools: list[dict[str, Any]] | None,
    tool_max_tokens: int,
) -> None:
    effective_max_tokens = None
    if max_completion_tokens is not None:
        effective_max_tokens = max_completion_tokens
    elif max_tokens is not None:
        effective_max_tokens = max_tokens
    elif tools is not None:
        effective_max_tokens = tool_max_tokens
        logger.warning(
            "No max_tokens set for tool request; using TOOL_MAX_TOKENS=%d",
            effective_max_tokens,
        )

    if effective_max_tokens is None:
        return

    if model.startswith("openai/"):
        kwargs["max_completion_tokens"] = effective_max_tokens
    else:
        kwargs["max_tokens"] = effective_max_tokens


def build_completion_kwargs(
    *,
    model: str,
    messages: list[dict[str, Any]],
    stream: bool,
    tool_max_tokens: int,
    temperature: float | None = None,
    max_tokens: int | None = None,
    max_completion_tokens: int | None = None,
    top_p: float | None = None,
    stop: str | list[str] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    parallel_tool_calls: bool | None = None,
    reasoning_effort: str | None = None,
    verbosity: str | None = None,
    stream_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build kwargs for the Dedalus chat completions API."""
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }

    if temperature is not None:
        kwargs["temperature"] = temperature

    _apply_token_limits(
        kwargs,
        model=model,
        max_tokens=max_tokens,
        max_completion_tokens=max_completion_tokens,
        tools=tools,
        tool_max_tokens=tool_max_tokens,
    )

    optional_fields: dict[str, Any] = {
        "top_p": top_p,
        "stop": stop,
        "tools": tools,
        "tool_choice": tool_choice,
        "parallel_tool_calls": parallel_tool_calls,
        "reasoning_effort": reasoning_effort,
        "verbosity": verbosity,
        "stream_options": stream_options,
    }
    kwargs.update({key: value for key, value in optional_fields.items() if value is not None})
    return kwargs


class DedalusRunner:
    """Runs chat completion requests against the Dedalus API."""

    def __init__(self, client: AsyncDedalus, tool_max_tokens: int) -> None:
        self.client = client
        self.tool_max_tokens = tool_max_tokens

    @overload
    async def create_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        stream: Literal[False] = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_completion_tokens: int | None = None,
        top_p: float | None = None,
        stop: str | list[str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        parallel_tool_calls: bool | None = None,
        reasoning_effort: str | None = None,
        verbosity: str | None = None,
        stream_options: dict[str, Any] | None = None,
    ) -> Any: ...

    @overload
    async def create_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        stream: Literal[True],
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_completion_tokens: int | None = None,
        top_p: float | None = None,
        stop: str | list[str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        parallel_tool_calls: bool | None = None,
        reasoning_effort: str | None = None,
        verbosity: str | None = None,
        stream_options: dict[str, Any] | None = None,
    ) -> AsyncGenerator[Any, None]: ...

    async def create_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_completion_tokens: int | None = None,
        top_p: float | None = None,
        stop: str | list[str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        parallel_tool_calls: bool | None = None,
        reasoning_effort: str | None = None,
        verbosity: str | None = None,
        stream_options: dict[str, Any] | None = None,
    ) -> AsyncGenerator[Any, None] | Any:
        kwargs = build_completion_kwargs(
            model=model,
            messages=messages,
            stream=stream,
            tool_max_tokens=self.tool_max_tokens,
            temperature=temperature,
            max_tokens=max_tokens,
            max_completion_tokens=max_completion_tokens,
            top_p=top_p,
            stop=stop,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            reasoning_effort=reasoning_effort,
            verbosity=verbosity,
            stream_options=stream_options,
        )

        logger.info(
            "Dedalus API call: model=%s, stream=%s, max_tokens=%s, tools=%d",
            model,
            stream,
            kwargs.get("max_tokens") or kwargs.get("max_completion_tokens"),
            len(tools) if tools else 0,
        )

        response = await self.client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
        return response


class DedalusClient:
    """Manages the Dedalus API client lifecycle."""

    def __init__(self) -> None:
        self._client: AsyncDedalus | None = None
        self._runner: DedalusRunner | None = None

    @property
    def client(self) -> AsyncDedalus:
        if self._client is None:
            config = get_config()
            self._client = AsyncDedalus(
                api_key=config.dedalus_api_key,
                base_url=config.dedalus_base_url,
                timeout=config.timeout,
                max_retries=config.max_retries,
            )
        return self._client

    @property
    def runner(self) -> DedalusRunner:
        if self._runner is None:
            config = get_config()
            self._runner = DedalusRunner(self.client, config.tool_max_tokens)
        return self._runner

    async def verify_connection(self) -> bool:
        """Verify API auth and connectivity without spending completion tokens."""
        await self.client.models.list()
        return True

    async def list_models(self) -> Any:
        """Return available models from the Dedalus API."""
        return await self.client.models.list()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._runner = None


def create_dedalus_client() -> DedalusClient:
    """Create a new Dedalus client instance."""
    return DedalusClient()
