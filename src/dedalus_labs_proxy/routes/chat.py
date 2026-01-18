"""Chat completions endpoint."""

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any, cast

import dedalus_labs
import orjson
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from dedalus_labs_proxy.config import get_config
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
    FunctionCall,
    ToolCall,
    ToolCallDelta,
)
from dedalus_labs_proxy.services.dedalus import global_client

router = APIRouter()

# SSE headers to prevent buffering and keep connections alive
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # Disable nginx buffering
    "Transfer-Encoding": "chunked",
}


def _extract_delta(  # noqa: C901
    chunk: Any,
) -> tuple[str | None, str | None, list[ToolCallDelta] | None, str | None]:
    """Extract delta information from a streaming chunk.

    Args:
        chunk: The streaming chunk from the Dedalus API.

    Returns:
        Tuple of (role, content, tool_calls, finish_reason).
    """
    role = None
    delta_content = None
    tool_calls = None
    finish_reason = None

    # Safety check for empty choices
    if not chunk.choices:
        return role, delta_content, tool_calls, finish_reason

    choice = chunk.choices[0]

    if hasattr(choice, "delta"):
        delta = choice.delta

        if hasattr(delta, "role") and delta.role:
            role = str(delta.role)

        if hasattr(delta, "content") and delta.content:
            delta_content = str(delta.content)

        if hasattr(delta, "tool_calls") and delta.tool_calls:
            tool_calls = []
            for tc in delta.tool_calls:
                thought_signature = None
                if hasattr(tc, "thought_signature") and tc.thought_signature:
                    thought_signature = tc.thought_signature

                tc_delta = ToolCallDelta(
                    index=tc.index if hasattr(tc, "index") else 0,
                    id=tc.id if hasattr(tc, "id") else None,
                    type=tc.type if hasattr(tc, "type") else None,
                    function=(
                        {
                            "name": (
                                tc.function.name
                                if hasattr(tc.function, "name") and tc.function.name
                                else None
                            ),
                            "arguments": (
                                tc.function.arguments
                                if hasattr(tc.function, "arguments")
                                and tc.function.arguments
                                else None
                            ),
                        }
                        if hasattr(tc, "function") and tc.function
                        else None
                    ),
                    thought_signature=thought_signature,
                )
                tool_calls.append(tc_delta)

    elif hasattr(choice, "message"):
        message = choice.message
        if hasattr(message, "role") and message.role:
            role = str(message.role)
        if hasattr(message, "content") and message.content:
            delta_content = str(message.content)

    if hasattr(choice, "finish_reason") and choice.finish_reason:
        finish_reason = str(choice.finish_reason)

    return role, delta_content, tool_calls, finish_reason


def _serialize_tool_choice(
    tool_choice: str | ToolChoiceObject | None,
) -> dict[str, Any] | None:
    """Serialize tool_choice for the Dedalus API.

    Args:
        tool_choice: The tool_choice value from the request.

    Returns:
        Serialized tool_choice or None.
    """
    if tool_choice is None:
        return None

    if isinstance(tool_choice, str):
        if tool_choice == "auto":
            return None
        elif tool_choice == "none":
            return {"type": "none"}
        elif tool_choice == "required":
            return {"type": "any"}
        else:
            return None

    return tool_choice.model_dump()


def _sanitize_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove or transform fields from tool schema for Google API compatibility.

    Google's API rejects schemas with $schema, additionalProperties, and other
    JSON Schema draft fields that OpenAI accepts. It also has issues with
    numeric constraint fields (like maxLength) - the Dedalus SDK may coerce
    string values back to integers, so we remove these fields entirely.

    Args:
        schema: The schema dict to sanitize.

    Returns:
        Sanitized schema dict.
    """
    # JSON Schema keywords that Google API doesn't accept
    # These are schema-level keywords, NOT property names
    disallowed_schema_keywords = {
        "$schema",
        "additionalProperties",
        # Numeric constraints that cause issues with Google API via Dedalus SDK
        "maxLength",
        "minLength",
        "maxItems",
        "minItems",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    }

    def _clean_dict(
        d: dict[str, Any], is_properties_dict: bool = False
    ) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for key, value in d.items():
            # Only skip disallowed keywords when NOT inside a "properties" dict
            # This ensures we don't accidentally remove user-defined property names
            # that happen to match JSON Schema keywords
            if not is_properties_dict and key in disallowed_schema_keywords:
                continue
            if isinstance(value, dict):
                # If this key is "properties", mark the next level as a properties dict
                cleaned[key] = _clean_dict(
                    value, is_properties_dict=(key == "properties")
                )
            elif isinstance(value, list):
                cleaned_list: list[Any] = []
                for item in value:
                    if isinstance(item, dict):
                        cleaned_list.append(_clean_dict(item, is_properties_dict=False))
                    else:
                        cleaned_list.append(item)
                cleaned[key] = cleaned_list
            else:
                cleaned[key] = value
        return cleaned

    return _clean_dict(schema)


def _sanitize_tools_for_google(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitize tool definitions for Google API compatibility.

    Args:
        tools: List of tool definitions.

    Returns:
        Sanitized tool definitions.
    """
    sanitized = []
    for tool in tools:
        tool_copy = tool.copy()
        if "function" in tool_copy and "parameters" in tool_copy["function"]:
            tool_copy["function"] = tool_copy["function"].copy()
            original_params = tool_copy["function"]["parameters"]
            sanitized_params = _sanitize_tool_schema(original_params)
            tool_copy["function"]["parameters"] = sanitized_params
            # Debug: log if we found any maxLength fields
            logger.debug(
                "Sanitized tool %s parameters",
                tool_copy["function"].get("name", "unknown"),
            )
        sanitized.append(tool_copy)
    return sanitized


def _is_google_model(model: str) -> bool:
    """Check if a model is a Google model.

    Args:
        model: The model name or identifier.

    Returns:
        True if the model is a Google model.
    """
    return model.startswith("google/") or model.startswith("gemini")


def _inject_thought_signatures(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inject dummy thought_signature for Google models when client doesn't preserve them.

    Google Gemini 3 models require thought_signature on tool calls in message history.
    If the client (e.g., OpenCode) doesn't preserve these, we inject a dummy signature
    that tells Google to skip validation.

    See: https://ai.google.dev/gemini-api/docs/thought-signatures

    Args:
        messages: List of message dicts.

    Returns:
        Messages with thought_signature injected where needed.
    """
    result = []
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            msg = msg.copy()
            tool_calls = []
            for idx, tc in enumerate(msg["tool_calls"]):
                tc = tc.copy()
                if not tc.get("thought_signature"):
                    if idx == 0:
                        # Google-approved magic string to skip signature validation
                        # See: https://ai.google.dev/gemini-api/docs/thought-signatures#faqs
                        # Base64-encoded because Dedalus SDK expects encoded signatures
                        # b64encode(b"skip_thought_signature_validator")
                        tc["thought_signature"] = (
                            "c2tpcF90aG91Z2h0X3NpZ25hdHVyZV92YWxpZGF0b3I="
                        )
                        logger.debug(
                            "Injected dummy thought_signature for tool call %s",
                            tc.get("function", {}).get("name", "unknown"),
                        )
                tool_calls.append(tc)
            msg["tool_calls"] = tool_calls
        result.append(msg)
    return result


async def _iter_with_keepalive(
    stream: Any,
    keepalive_interval: float,
) -> AsyncGenerator[Any, None]:
    """Wrap an async iterator to yield keepalive pings during long waits.

    This prevents HTTP connections from being closed by proxies or clients
    when the upstream API takes time to generate large responses (e.g., large
    file writes via tool calls).

    Args:
        stream: The async iterator to wrap.
        keepalive_interval: Seconds to wait before sending a keepalive ping.

    Yields:
        Items from the stream, or None to indicate a keepalive ping should be sent.
    """
    stream_iter = stream.__aiter__()
    # Track the pending __anext__ task to avoid cancellation issues
    pending_next: asyncio.Task[Any] | None = None

    while True:
        try:
            # Create task for next item if we don't have one pending
            if pending_next is None:
                pending_next = asyncio.create_task(stream_iter.__anext__())

            # Wait for the next chunk with a timeout, but don't cancel the task
            try:
                chunk = await asyncio.wait_for(
                    asyncio.shield(pending_next),
                    timeout=keepalive_interval,
                )
                pending_next = None  # Task completed, clear it
                yield chunk
            except TimeoutError:
                # Task still pending - yield None to signal keepalive ping
                yield None
                # Continue loop to wait for the same task again
        except StopAsyncIteration:
            # Stream exhausted
            break


async def _stream_google_with_tools(
    request: ChatCompletionRequest,
    config: Any,
) -> AsyncGenerator[str, None]:
    """Handle streaming for Google models with tools by falling back to non-streaming.

    Google models via Dedalus API don't properly support streaming with function calling.
    This workaround makes a non-streaming request and simulates streaming output.

    Args:
        request: The chat completion request.
        config: The application configuration.

    Yields:
        SSE-formatted chunks that simulate streaming.
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    dedalus_model = request.model
    keepalive_interval = config.stream_keepalive_interval

    logger.info(
        "Google model with tools detected, using non-streaming fallback for: %s",
        dedalus_model,
    )

    try:
        messages = [msg.model_dump(exclude_none=True) for msg in request.messages]

        # Inject thought_signature for Google models (required for Gemini 3)
        messages = _inject_thought_signatures(messages)

        tools = (
            [tool.model_dump(exclude_none=True) for tool in request.tools]
            if request.tools
            else None
        )

        # Sanitize tools for Google API compatibility
        if tools:
            logger.debug("Sanitizing %d tools for Google API", len(tools))
            tools = _sanitize_tools_for_google(tools)

        # Create the API call as a task so we can send keepalive pings while waiting
        api_task = asyncio.create_task(
            global_client.runner.create_completion(
                model=dedalus_model,
                messages=messages,
                stream=False,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                max_completion_tokens=request.max_completion_tokens,
                top_p=request.top_p,
                stop=request.stop,
                tools=tools,
                tool_choice=_serialize_tool_choice(request.tool_choice),
                parallel_tool_calls=request.parallel_tool_calls,
                reasoning_effort=request.reasoning_effort,
                verbosity=request.verbosity,
            )
        )

        # Send keepalive pings while waiting for the API response
        while not api_task.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(api_task), timeout=keepalive_interval
                )
            except TimeoutError:
                # API call still in progress - send keepalive ping
                yield ": ping\n\n"

        # Get the result (will raise if the task failed)
        dedalus_response = cast(Any, await api_task)

        response_message = dedalus_response.choices[0].message
        content = getattr(response_message, "content", None)
        finish_reason = (
            str(dedalus_response.choices[0].finish_reason)
            if dedalus_response.choices[0].finish_reason
            else "stop"
        )

        # Extract tool calls if present
        tool_call_deltas = None
        if hasattr(response_message, "tool_calls") and response_message.tool_calls:
            tool_call_deltas = []
            for idx, tc in enumerate(response_message.tool_calls):
                thought_signature = None
                if hasattr(tc, "thought_signature") and tc.thought_signature:
                    thought_signature = tc.thought_signature

                tool_call_deltas.append(
                    ToolCallDelta(
                        index=idx,
                        id=tc.id,
                        type=tc.type if hasattr(tc, "type") else "function",
                        function={
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                        thought_signature=thought_signature,
                    )
                )

        # Simulate streaming: first chunk with role
        first_chunk = ChatCompletionChunk(
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
        yield f"data: {first_chunk.model_dump_json(exclude_none=True)}\n\n"

        # Second chunk with content and/or tool calls
        if content or tool_call_deltas:
            content_chunk = ChatCompletionChunk(
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
            yield f"data: {content_chunk.model_dump_json(exclude_none=True)}\n\n"

        # Final chunk with finish_reason
        final_chunk = ChatCompletionChunk(
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
        yield f"data: {final_chunk.model_dump_json(exclude_none=True)}\n\n"
        yield "data: [DONE]\n\n"

    except dedalus_labs.AuthenticationError:
        logger.error(
            "Authentication failed during Google streaming fallback: %s", request.model
        )
        error_data = {"error": {"message": "Authentication failed: Invalid API key"}}
        yield f"data: {orjson.dumps(error_data).decode()}\n\n"
    except dedalus_labs.APITimeoutError as e:
        logger.error("Request timed out during Google streaming fallback: %s", str(e))
        error_data = {
            "error": {
                "message": "Request timed out. Try reducing the complexity of your query."
            }
        }
        yield f"data: {orjson.dumps(error_data).decode()}\n\n"
    except dedalus_labs.APIConnectionError as e:
        logger.error("Connection failed during Google streaming fallback: %s", str(e))
        error_data = {
            "error": {"message": f"Failed to connect to Dedalus API: {str(e)}"}
        }
        yield f"data: {orjson.dumps(error_data).decode()}\n\n"
    except dedalus_labs.APIStatusError as e:
        logger.error(
            "API error during Google streaming fallback (status %d): %s",
            e.status_code,
            e.message,
        )
        error_data = {"error": {"message": e.message, "code": str(e.status_code)}}
        yield f"data: {orjson.dumps(error_data).decode()}\n\n"


async def _stream_chat_completion(
    request: ChatCompletionRequest,
) -> AsyncGenerator[str, None]:
    """Stream chat completion chunks.

    Args:
        request: The chat completion request.

    Yields:
        SSE-formatted chunks.
    """
    config = get_config()
    dedalus_model = request.model

    # Google models don't support streaming with tools via Dedalus API
    # Fall back to non-streaming and simulate streaming response
    if _is_google_model(dedalus_model) and request.tools:
        async for chunk in _stream_google_with_tools(request, config):
            yield chunk
        return

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    try:
        messages = [msg.model_dump(exclude_none=True) for msg in request.messages]

        tools = (
            [tool.model_dump(exclude_none=True) for tool in request.tools]
            if request.tools
            else None
        )

        if tools:
            logger.debug(
                "First tool being sent: %s", orjson.dumps(tools[0]).decode()[:500]
            )

        stream = await global_client.runner.create_completion(
            model=dedalus_model,
            messages=messages,
            stream=True,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            max_completion_tokens=request.max_completion_tokens,
            top_p=request.top_p,
            stop=request.stop,
            tools=tools,
            tool_choice=_serialize_tool_choice(request.tool_choice),
            parallel_tool_calls=request.parallel_tool_calls,
            reasoning_effort=request.reasoning_effort,
            verbosity=request.verbosity,
        )

        # Wrap stream with keepalive to prevent connection drops during large responses
        keepalive_interval = config.stream_keepalive_interval
        chunk_count = 0
        tool_call_args_size: dict[int, int] = {}  # Track accumulated size per tool call
        final_finish_reason = None

        async for chunk in _iter_with_keepalive(stream, keepalive_interval):
            # None signals a keepalive ping (no data received within interval)
            if chunk is None:
                # SSE comment - ignored by clients but keeps connection alive
                logger.debug("Sending keepalive ping (chunk %d)", chunk_count)
                yield ": ping\n\n"
                continue

            chunk_count += 1
            role, delta_content, tool_calls, finish_reason = _extract_delta(chunk)

            # Track tool call argument sizes for debugging
            if tool_calls:
                for tc in tool_calls:
                    if tc.function and tc.function.get("arguments"):
                        args_chunk = tc.function["arguments"]
                        idx = tc.index
                        tool_call_args_size[idx] = tool_call_args_size.get(
                            idx, 0
                        ) + len(args_chunk)
                        if chunk_count <= 5 or chunk_count % 100 == 0:
                            logger.debug(
                                "Tool call[%d] args chunk: +%d bytes (total: %d)",
                                idx,
                                len(args_chunk),
                                tool_call_args_size[idx],
                            )

            if finish_reason:
                final_finish_reason = finish_reason
                if finish_reason == "length":
                    logger.warning(
                        "Stream TRUNCATED (finish_reason=length) after %d chunks, "
                        "tool_call_sizes=%s - response exceeded max_tokens limit!",
                        chunk_count,
                        tool_call_args_size,
                    )
                else:
                    logger.info(
                        "Stream finish_reason=%s after %d chunks, tool_call_sizes=%s",
                        finish_reason,
                        chunk_count,
                        tool_call_args_size,
                    )

            delta = ChatCompletionChunkDelta(
                role=role,
                content=delta_content,
                tool_calls=tool_calls,
            )

            sse_chunk = ChatCompletionChunk(
                id=completion_id,
                created=created,
                model=request.model,
                choices=[
                    ChatCompletionChunkChoice(
                        index=0,
                        delta=delta,
                        finish_reason=finish_reason,
                    )
                ],
            )

            yield f"data: {sse_chunk.model_dump_json(exclude_none=True)}\n\n"

        # Log summary if we didn't see a finish_reason (abnormal termination)
        if final_finish_reason is None:
            logger.warning(
                "Stream ended without finish_reason after %d chunks, tool_call_sizes=%s",
                chunk_count,
                tool_call_args_size,
            )

        yield "data: [DONE]\n\n"

    except dedalus_labs.AuthenticationError:
        logger.error(
            "Authentication failed during streaming for model: %s", request.model
        )
        error_data = {"error": {"message": "Authentication failed: Invalid API key"}}
        yield f"data: {orjson.dumps(error_data).decode()}\n\n"
    except dedalus_labs.APITimeoutError as e:
        logger.error("Request timed out during streaming: %s", str(e))
        error_data = {
            "error": {
                "message": "Request timed out. Try reducing the complexity of your query."
            }
        }
        yield f"data: {orjson.dumps(error_data).decode()}\n\n"
    except dedalus_labs.APIConnectionError as e:
        logger.error("Connection failed during streaming: %s", str(e))
        error_data = {
            "error": {"message": f"Failed to connect to Dedalus API: {str(e)}"}
        }
        yield f"data: {orjson.dumps(error_data).decode()}\n\n"
    except dedalus_labs.APIStatusError as e:
        logger.error(
            "API error during streaming (status %d): %s", e.status_code, e.message
        )
        error_data = {"error": {"message": e.message, "code": str(e.status_code)}}
        yield f"data: {orjson.dumps(error_data).decode()}\n\n"


def _extract_tool_calls(message: Any) -> list[ToolCall] | None:
    """Extract tool calls from a message.

    Args:
        message: The message object from the response.

    Returns:
        List of ToolCall objects or None.
    """
    if not hasattr(message, "tool_calls") or not message.tool_calls:
        return None

    tool_calls = []
    for tc in message.tool_calls:
        thought_signature = None
        if hasattr(tc, "thought_signature") and tc.thought_signature:
            thought_signature = tc.thought_signature

        tool_call = ToolCall(
            id=tc.id,
            type=tc.type if hasattr(tc, "type") else "function",
            function=FunctionCall(
                name=tc.function.name,
                arguments=tc.function.arguments,
            ),
            thought_signature=thought_signature,
        )
        tool_calls.append(tool_call)
    return tool_calls


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
) -> ChatCompletionResponse | StreamingResponse:
    """Handle chat completion requests.

    Args:
        request: The chat completion request.

    Returns:
        Chat completion response or streaming response.

    Raises:
        HTTPException: On validation or API errors.
    """
    logger.info(
        "Chat completion: model=%s, stream=%s, messages=%d, tools=%d",
        request.model,
        request.stream,
        len(request.messages),
        len(request.tools) if request.tools else 0,
    )

    logger.debug(
        "Request details: temp=%s, max_tokens=%s, max_completion_tokens=%s, "
        "tool_choice=%s, parallel_tool_calls=%s",
        request.temperature,
        request.max_tokens,
        request.max_completion_tokens,
        request.tool_choice,
        request.parallel_tool_calls,
    )
    for i, msg in enumerate(request.messages):
        has_thought_sig = False
        if msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.get("thought_signature"):
                    has_thought_sig = True
                    break
        logger.debug(
            "  message[%d]: role=%s, has_content=%s, tool_calls=%s, has_thought_sig=%s",
            i,
            msg.role,
            bool(msg.content),
            bool(msg.tool_calls),
            has_thought_sig,
        )
    if request.tools:
        tool_names = [t.function.name for t in request.tools[:5]]
        logger.debug(
            "  tools: %s%s", tool_names, "..." if len(request.tools) > 5 else ""
        )

    if request.stream:
        return StreamingResponse(
            _stream_chat_completion(request),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    dedalus_model = request.model

    try:
        messages = [msg.model_dump(exclude_none=True) for msg in request.messages]

        # Inject thought_signature for Google models (required for Gemini 3)
        if _is_google_model(dedalus_model):
            messages = _inject_thought_signatures(messages)

        tools = (
            [tool.model_dump(exclude_none=True) for tool in request.tools]
            if request.tools
            else None
        )

        # Sanitize tools for Google API compatibility
        if tools and _is_google_model(dedalus_model):
            tools = _sanitize_tools_for_google(tools)

        dedalus_response = cast(
            Any,
            await global_client.runner.create_completion(
                model=dedalus_model,
                messages=messages,
                stream=False,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                max_completion_tokens=request.max_completion_tokens,
                top_p=request.top_p,
                stop=request.stop,
                tools=tools,
                tool_choice=_serialize_tool_choice(request.tool_choice),
                parallel_tool_calls=request.parallel_tool_calls,
                reasoning_effort=request.reasoning_effort,
                verbosity=request.verbosity,
            ),
        )

        logger.info(
            "Chat completion successful: id=%s, tokens=%d",
            dedalus_response.id,
            dedalus_response.usage.total_tokens,
        )

        response_message = dedalus_response.choices[0].message
        content = (
            response_message.content if hasattr(response_message, "content") else None
        )
        tool_calls = _extract_tool_calls(response_message)

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
                        tool_calls=tool_calls,
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
    except dedalus_labs.AuthenticationError:
        logger.error("Authentication failed for model: %s", dedalus_model)
        raise HTTPException(
            status_code=401, detail="Authentication failed: Invalid API key"
        ) from None
    except dedalus_labs.APITimeoutError as e:
        logger.error("Request timed out for model %s: %s", dedalus_model, str(e))
        raise HTTPException(
            status_code=504,
            detail="Request timed out. Try reducing the complexity of your query.",
        ) from None
    except dedalus_labs.APIConnectionError as e:
        logger.error("Connection failed for model %s: %s", dedalus_model, str(e))
        raise HTTPException(
            status_code=503, detail=f"Failed to connect to Dedalus API: {str(e)}"
        ) from None
    except dedalus_labs.APIStatusError as e:
        logger.error(
            "API error for model %s (status %d): %s",
            dedalus_model,
            e.status_code,
            e.message,
        )
        raise HTTPException(status_code=e.status_code, detail=e.message) from None
