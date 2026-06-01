"""Chat completion orchestration service."""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import dedalus_labs
import orjson
from fastapi import HTTPException

from dedalus_labs_proxy.config import Config, get_config
from dedalus_labs_proxy.logging import logger
from dedalus_labs_proxy.models.requests import ChatCompletionRequest, ToolChoiceObject
from dedalus_labs_proxy.models.responses import (
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatCompletionUsage,
    ChatMessageResponse,
    ToolCallDelta,
)
from dedalus_labs_proxy.services.completion.adapters import (
    ChunkAdapter,
    extract_tool_calls,
    tool_call_from_sdk,
)
from dedalus_labs_proxy.services.completion.errors import (
    map_dedalus_exception_to_http,
    stream_dedalus_errors,
)
from dedalus_labs_proxy.services.completion.google_compat import (
    is_google_model,
    prepare_google_request,
)
from dedalus_labs_proxy.services.completion.sse import (
    SSE_DONE,
    SSE_PING,
    format_chunk,
    yield_sse_error,
)
from dedalus_labs_proxy.services.completion.streaming_keepalive import (
    iter_with_keepalive,
)
from dedalus_labs_proxy.services.dedalus import DedalusClient, DedalusRunner

_completion_logger = logging.getLogger("dedalus-proxy")


def serialize_tool_choice(
    tool_choice: str | ToolChoiceObject | None,
) -> str | dict[str, Any] | None:
    """Serialize tool_choice for the Dedalus API."""
    if tool_choice is None:
        return None

    if isinstance(tool_choice, str):
        if tool_choice == "auto":
            return None
        if tool_choice == "none":
            return {"type": "none"}
        if tool_choice == "required":
            return {"type": "any"}
        return tool_choice

    return tool_choice.model_dump()


def _log_request_debug(request: ChatCompletionRequest) -> None:
    if not _completion_logger.isEnabledFor(logging.DEBUG):
        return

    _completion_logger.debug(
        "Request details: temp=%s, max_tokens=%s, max_completion_tokens=%s, "
        "tool_choice=%s, parallel_tool_calls=%s",
        request.temperature,
        request.max_tokens,
        request.max_completion_tokens,
        request.tool_choice,
        request.parallel_tool_calls,
    )
    for i, msg in enumerate(request.messages):
        has_thought_sig = bool(
            msg.tool_calls
            and any(tc.get("thought_signature") for tc in msg.tool_calls)
        )
        _completion_logger.debug(
            "  message[%d]: role=%s, has_content=%s, tool_calls=%s, has_thought_sig=%s",
            i,
            msg.role,
            bool(msg.content),
            bool(msg.tool_calls),
            has_thought_sig,
        )
    if request.tools:
        tool_names = [t.function.name for t in request.tools[:5]]
        _completion_logger.debug(
            "  tools: %s%s", tool_names, "..." if len(request.tools) > 5 else ""
        )


def _apply_server_defaults(
    request: ChatCompletionRequest, config: Config
) -> ChatCompletionRequest:
    updates: dict[str, Any] = {}
    if request.temperature is None:
        updates["temperature"] = config.temperature
    if request.max_tokens is None and request.max_completion_tokens is None:
        updates["max_tokens"] = config.max_tokens
    if not updates:
        return request
    return request.model_copy(update=updates)


def _runner_kwargs(prepared: "PreparedRequest", *, stream: bool) -> dict[str, Any]:
    return {
        "model": prepared.model,
        "messages": prepared.messages,
        "stream": stream,
        "temperature": prepared.temperature,
        "max_tokens": prepared.max_tokens,
        "max_completion_tokens": prepared.max_completion_tokens,
        "top_p": prepared.top_p,
        "stop": prepared.stop,
        "tools": prepared.tools,
        "tool_choice": prepared.tool_choice,
        "parallel_tool_calls": prepared.parallel_tool_calls,
        "reasoning_effort": prepared.reasoning_effort,
        "verbosity": prepared.verbosity,
    }


def _track_tool_call_sizes(
    tool_calls: list[ToolCallDelta] | None,
    tool_call_args_size: dict[int, int],
) -> None:
    if not tool_calls:
        return
    for tc in tool_calls:
        if tc.function and tc.function.get("arguments"):
            idx = tc.index
            tool_call_args_size[idx] = tool_call_args_size.get(idx, 0) + len(
                tc.function["arguments"]
            )


def _log_stream_finish_reason(
    finish_reason: str,
    chunk_count: int,
    tool_call_args_size: dict[int, int],
) -> None:
    if finish_reason == "length":
        logger.warning(
            "Stream TRUNCATED (finish_reason=length) after %d chunks, "
            "tool_call_sizes=%s",
            chunk_count,
            tool_call_args_size,
        )
        return
    logger.info(
        "Stream finish_reason=%s after %d chunks, tool_call_sizes=%s",
        finish_reason,
        chunk_count,
        tool_call_args_size,
    )


def _build_response_from_dedalus(
    dedalus_response: Any, request: ChatCompletionRequest
) -> ChatCompletionResponse:
    if not dedalus_response.choices:
        raise HTTPException(status_code=502, detail="Upstream returned empty choices")

    response_message = dedalus_response.choices[0].message
    content = (
        response_message.content if hasattr(response_message, "content") else None
    )
    finish_reason = dedalus_response.choices[0].finish_reason
    if finish_reason:
        finish_reason = str(finish_reason)

    return ChatCompletionResponse(
        id=dedalus_response.id,
        created=int(time.time()),
        model=request.model,
        choices=[
            ChatCompletionResponseChoice(
                index=0,
                message=ChatMessageResponse(
                    role=response_message.role,
                    content=content,
                    tool_calls=extract_tool_calls(response_message),
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=dedalus_response.usage.prompt_tokens,
            completion_tokens=dedalus_response.usage.completion_tokens,
            total_tokens=dedalus_response.usage.total_tokens,
        ),
    )


class PreparedRequest:
    """Normalized request payload for upstream completion calls."""

    def __init__(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
        temperature: float | None,
        max_tokens: int | None,
        max_completion_tokens: int | None,
        top_p: float | None,
        stop: str | list[str] | None,
        parallel_tool_calls: bool | None,
        reasoning_effort: str | None,
        verbosity: str | None,
    ) -> None:
        self.model = model
        self.messages = messages
        self.tools = tools
        self.tool_choice = tool_choice
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_completion_tokens = max_completion_tokens
        self.top_p = top_p
        self.stop = stop
        self.parallel_tool_calls = parallel_tool_calls
        self.reasoning_effort = reasoning_effort
        self.verbosity = verbosity


class ChatCompletionService:
    """Orchestrates chat completion requests."""

    def __init__(self, client: DedalusClient) -> None:
        self._client = client

    @property
    def runner(self) -> DedalusRunner:
        return self._client.runner

    def prepare_request(self, request: ChatCompletionRequest) -> PreparedRequest:
        config = get_config()
        request = _apply_server_defaults(request, config)

        messages = [msg.model_dump(exclude_none=True) for msg in request.messages]
        tools = (
            [tool.model_dump(exclude_none=True) for tool in request.tools]
            if request.tools
            else None
        )
        messages, tools = prepare_google_request(request.model, messages, tools)

        return PreparedRequest(
            model=request.model,
            messages=messages,
            tools=tools,
            tool_choice=serialize_tool_choice(request.tool_choice),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            max_completion_tokens=request.max_completion_tokens,
            top_p=request.top_p,
            stop=request.stop,
            parallel_tool_calls=request.parallel_tool_calls,
            reasoning_effort=request.reasoning_effort,
            verbosity=request.verbosity,
        )

    def log_request(self, request: ChatCompletionRequest) -> None:
        logger.info(
            "Chat completion: model=%s, stream=%s, messages=%d, tools=%d",
            request.model,
            request.stream,
            len(request.messages),
            len(request.tools) if request.tools else 0,
        )
        _log_request_debug(request)

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        prepared = self.prepare_request(request)
        try:
            dedalus_response = await self.runner.create_completion(
                **_runner_kwargs(prepared, stream=False)
            )
        except (
            dedalus_labs.AuthenticationError,
            dedalus_labs.APITimeoutError,
            dedalus_labs.APIConnectionError,
            dedalus_labs.APIStatusError,
        ) as exc:
            raise map_dedalus_exception_to_http(exc) from None

        logger.info(
            "Chat completion successful: id=%s, tokens=%d",
            dedalus_response.id,
            dedalus_response.usage.total_tokens,
        )
        return _build_response_from_dedalus(dedalus_response, request)

    async def stream(self, request: ChatCompletionRequest) -> AsyncGenerator[str, None]:
        if is_google_model(request.model) and request.tools:
            async for chunk in self._stream_google_with_tools(request):
                yield chunk
            return

        async for chunk in self._stream_default(request):
            yield chunk

    async def _stream_default(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[str, None]:
        config = get_config()
        prepared = self.prepare_request(request)
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())

        try:
            if prepared.tools:
                logger.debug(
                    "First tool being sent: %s",
                    orjson.dumps(prepared.tools[0]).decode()[:500],
                )

            stream = await self.runner.create_completion(
                **_runner_kwargs(prepared, stream=True)
            )

            keepalive_interval = config.stream_keepalive_interval
            chunk_count = 0
            tool_call_args_size: dict[int, int] = {}
            final_finish_reason = None

            async for chunk in iter_with_keepalive(stream, keepalive_interval):
                if chunk is None:
                    logger.debug("Sending keepalive ping (chunk %d)", chunk_count)
                    yield SSE_PING
                    continue

                chunk_count += 1
                parsed = ChunkAdapter.parse(chunk)
                if parsed is None:
                    continue

                if parsed.tool_calls:
                    _track_tool_call_sizes(parsed.tool_calls, tool_call_args_size)

                if parsed.finish_reason:
                    final_finish_reason = parsed.finish_reason
                    _log_stream_finish_reason(
                        parsed.finish_reason, chunk_count, tool_call_args_size
                    )

                sse_chunk = ChatCompletionChunk(
                    id=completion_id,
                    created=created,
                    model=request.model,
                    choices=[
                        ChatCompletionChunkChoice(
                            index=0,
                            delta=ChatCompletionChunkDelta(
                                role=parsed.role,
                                content=parsed.content,
                                tool_calls=parsed.tool_calls,
                            ),
                            finish_reason=parsed.finish_reason,
                        )
                    ],
                )
                yield format_chunk(sse_chunk)

            if final_finish_reason is None:
                logger.warning(
                    "Stream ended without finish_reason after %d chunks, tool_call_sizes=%s",
                    chunk_count,
                    tool_call_args_size,
                )

            yield SSE_DONE

        except (
            dedalus_labs.AuthenticationError,
            dedalus_labs.APITimeoutError,
            dedalus_labs.APIConnectionError,
            dedalus_labs.APIStatusError,
        ) as exc:
            logger.error("Streaming error for model %s: %s", request.model, exc)
            async for event in stream_dedalus_errors(exc):
                yield event

    async def _stream_google_with_tools(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[str, None]:
        config = get_config()
        prepared = self.prepare_request(request)
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())
        keepalive_interval = config.stream_keepalive_interval

        logger.info(
            "Google model with tools detected, using non-streaming fallback for: %s",
            prepared.model,
        )

        try:
            api_task = asyncio.create_task(
                self.runner.create_completion(**_runner_kwargs(prepared, stream=False))
            )

            while not api_task.done():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(api_task), timeout=keepalive_interval
                    )
                except TimeoutError:
                    yield SSE_PING

            dedalus_response = await api_task

            if not dedalus_response.choices:
                async for event in yield_sse_error(
                    {"error": {"message": "Upstream returned empty choices"}}
                ):
                    yield event
                return

            response_message = dedalus_response.choices[0].message
            content = getattr(response_message, "content", None)
            finish_reason = (
                str(dedalus_response.choices[0].finish_reason)
                if dedalus_response.choices[0].finish_reason
                else "stop"
            )

            tool_call_deltas: list[ToolCallDelta] | None = None
            if hasattr(response_message, "tool_calls") and response_message.tool_calls:
                tool_call_deltas = []
                for idx, tc in enumerate(response_message.tool_calls):
                    mapped = tool_call_from_sdk(tc)
                    tool_call_deltas.append(
                        ToolCallDelta(
                            index=idx,
                            id=mapped.id,
                            type=mapped.type,
                            function={
                                "name": mapped.function.name,
                                "arguments": mapped.function.arguments,
                            },
                            thought_signature=mapped.thought_signature,
                        )
                    )

            yield format_chunk(
                ChatCompletionChunk(
                    id=completion_id,
                    created=created,
                    model=request.model,
                    choices=[
                        ChatCompletionChunkChoice(
                            index=0,
                            delta=ChatCompletionChunkDelta(role="assistant"),
                            finish_reason=None,
                        )
                    ],
                )
            )

            if content or tool_call_deltas:
                yield format_chunk(
                    ChatCompletionChunk(
                        id=completion_id,
                        created=created,
                        model=request.model,
                        choices=[
                            ChatCompletionChunkChoice(
                                index=0,
                                delta=ChatCompletionChunkDelta(
                                    content=content,
                                    tool_calls=tool_call_deltas,
                                ),
                                finish_reason=None,
                            )
                        ],
                    )
                )

            yield format_chunk(
                ChatCompletionChunk(
                    id=completion_id,
                    created=created,
                    model=request.model,
                    choices=[
                        ChatCompletionChunkChoice(
                            index=0,
                            delta=ChatCompletionChunkDelta(),
                            finish_reason=finish_reason,
                        )
                    ],
                )
            )
            yield SSE_DONE

        except (
            dedalus_labs.AuthenticationError,
            dedalus_labs.APITimeoutError,
            dedalus_labs.APIConnectionError,
            dedalus_labs.APIStatusError,
        ) as exc:
            logger.error(
                "Google streaming fallback error for model %s: %s", request.model, exc
            )
            async for event in stream_dedalus_errors(exc):
                yield event
