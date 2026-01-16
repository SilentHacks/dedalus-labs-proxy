"""Chat completions endpoint."""

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

    if not config.is_valid_model(request.model):
        logger.warning("Invalid model requested: %s", request.model)
        error_data = {"error": {"message": f"Model '{request.model}' not supported"}}
        yield f"data: {orjson.dumps(error_data).decode()}\n\n"
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
            model=config.get_model_name(request.model),
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

        async for chunk in stream:
            role, delta_content, tool_calls, finish_reason = _extract_delta(chunk)

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
            "error": {"message": "Request timed out. Try reducing the complexity of your query."}
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
        tool_call = ToolCall(
            id=tc.id,
            type=tc.type if hasattr(tc, "type") else "function",
            function=FunctionCall(
                name=tc.function.name,
                arguments=tc.function.arguments,
            ),
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
    config = get_config()

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
        logger.debug(
            "  message[%d]: role=%s, has_content=%s, tool_calls=%s",
            i,
            msg.role,
            bool(msg.content),
            bool(msg.tool_calls),
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
        )

    dedalus_model = config.get_model_name(request.model)

    if not config.is_valid_model(request.model):
        raise HTTPException(
            status_code=400, detail=f"Model '{request.model}' not supported"
        )

    try:
        messages = [msg.model_dump(exclude_none=True) for msg in request.messages]

        tools = (
            [tool.model_dump(exclude_none=True) for tool in request.tools]
            if request.tools
            else None
        )

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
