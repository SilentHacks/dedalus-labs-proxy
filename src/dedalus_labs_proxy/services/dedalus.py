"""Dedalus SDK wrapper service."""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from dedalus_labs import AsyncDedalus

from dedalus_labs_proxy.config import get_config

logger = logging.getLogger("dedalus-proxy")


class DedalusRunner:
    """Runs chat completion requests against the Dedalus API."""

    def __init__(self, client: AsyncDedalus) -> None:
        """Initialize with a Dedalus client.

        Args:
            client: AsyncDedalus client instance.
        """
        self.client = client

    async def create_completion(  # noqa: C901
        self,
        model: str,
        messages: list[dict[str, Any]],
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
    ) -> AsyncGenerator[Any, None] | Any:
        """Create a chat completion.

        Args:
            model: Model identifier.
            messages: Conversation messages.
            stream: Whether to stream the response.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            max_completion_tokens: Alternative max tokens parameter.
            top_p: Top-p sampling parameter.
            stop: Stop sequences.
            tools: Tool definitions.
            tool_choice: Tool choice strategy.
            parallel_tool_calls: Whether to allow parallel tool calls.
            reasoning_effort: Reasoning effort level.
            verbosity: Response verbosity level.

        Returns:
            The completion response or an async generator for streaming.
        """
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }

        if temperature is not None:
            kwargs["temperature"] = temperature

        # Handle max_tokens parameter - prefer max_completion_tokens
        effective_max_tokens = None
        if max_completion_tokens is not None:
            effective_max_tokens = max_completion_tokens
        elif max_tokens is not None:
            effective_max_tokens = max_tokens
        elif tools is not None:
            # Set default max_tokens for tool-enabled requests
            # Use a high default to support large file writes
            from dedalus_labs_proxy.config import get_config

            config = get_config()
            effective_max_tokens = config.tool_max_tokens
            logger.info(
                "Setting max_tokens=%d for tool-enabled request", effective_max_tokens
            )

        if effective_max_tokens is not None:
            if model.startswith("openai/"):
                kwargs["max_completion_tokens"] = effective_max_tokens
            else:
                kwargs["max_tokens"] = effective_max_tokens
                kwargs["max_completion_tokens"] = effective_max_tokens

        logger.info(
            "Dedalus API call: model=%s, stream=%s, max_tokens=%s, tools=%d",
            model,
            stream,
            kwargs.get("max_tokens"),
            len(tools) if tools else 0,
        )

        if top_p is not None:
            kwargs["top_p"] = top_p
        if stop is not None:
            kwargs["stop"] = stop
        if tools is not None:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if parallel_tool_calls is not None:
            kwargs["parallel_tool_calls"] = parallel_tool_calls
        if reasoning_effort is not None:
            kwargs["reasoning_effort"] = reasoning_effort
        if verbosity is not None:
            kwargs["verbosity"] = verbosity

        response = await self.client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
        return response


class DedalusClient:
    """Manages the Dedalus API client lifecycle."""

    def __init__(self) -> None:
        """Initialize the client manager."""
        self._client: AsyncDedalus | None = None

    @property
    def client(self) -> AsyncDedalus:
        """Get the Dedalus client, creating it if needed."""
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
        """Get a runner instance for the current client."""
        return DedalusRunner(self.client)

    async def verify_connection(self) -> bool:
        """Verify the API connection is working.

        Returns:
            True if connection is verified.

        Raises:
            AuthenticationError: If API key is invalid.
            APIConnectionError: If connection fails.
        """
        await self.client.chat.completions.create(  # type: ignore[call-overload]
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=1,
        )
        return True

    async def close(self) -> None:
        """Close the client connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None


# Global client instance
global_client = DedalusClient()
