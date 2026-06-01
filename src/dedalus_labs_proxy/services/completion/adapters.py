"""Adapters between Dedalus SDK responses and OpenAI-compatible models."""

from dataclasses import dataclass
from typing import Any

from dedalus_labs_proxy.models.responses import (
    FunctionCall,
    ToolCall,
    ToolCallDelta,
)


@dataclass
class StreamDelta:
    """Normalized streaming delta from an upstream chunk."""

    role: str | None = None
    content: str | None = None
    tool_calls: list[ToolCallDelta] | None = None
    finish_reason: str | None = None


def _tool_call_delta_from_sdk(tc: Any) -> ToolCallDelta:
    thought_signature = None
    if hasattr(tc, "thought_signature") and tc.thought_signature:
        thought_signature = tc.thought_signature

    function = None
    if hasattr(tc, "function") and tc.function:
        function = {
            "name": (
                tc.function.name
                if hasattr(tc.function, "name") and tc.function.name
                else None
            ),
            "arguments": (
                tc.function.arguments
                if hasattr(tc.function, "arguments") and tc.function.arguments
                else None
            ),
        }

    return ToolCallDelta(
        index=tc.index if hasattr(tc, "index") else 0,
        id=tc.id if hasattr(tc, "id") else None,
        type=tc.type if hasattr(tc, "type") else None,
        function=function,
        thought_signature=thought_signature,
    )


def tool_call_from_sdk(tc: Any) -> ToolCall:
    thought_signature = None
    if hasattr(tc, "thought_signature") and tc.thought_signature:
        thought_signature = tc.thought_signature

    return ToolCall(
        id=tc.id,
        type=tc.type if hasattr(tc, "type") else "function",
        function=FunctionCall(
            name=tc.function.name,
            arguments=tc.function.arguments,
        ),
        thought_signature=thought_signature,
    )


class ChunkAdapter:
    """Parse Dedalus SDK streaming chunks into normalized deltas."""

    @staticmethod
    def parse(chunk: Any) -> StreamDelta | None:
        if not chunk.choices:
            return StreamDelta()

        choice = chunk.choices[0]
        delta = StreamDelta()

        if hasattr(choice, "delta"):
            sdk_delta = choice.delta
            if hasattr(sdk_delta, "role") and sdk_delta.role:
                delta.role = str(sdk_delta.role)
            if hasattr(sdk_delta, "content") and sdk_delta.content:
                delta.content = str(sdk_delta.content)
            if hasattr(sdk_delta, "tool_calls") and sdk_delta.tool_calls:
                delta.tool_calls = [
                    _tool_call_delta_from_sdk(tc) for tc in sdk_delta.tool_calls
                ]
        elif hasattr(choice, "message"):
            message = choice.message
            if hasattr(message, "role") and message.role:
                delta.role = str(message.role)
            if hasattr(message, "content") and message.content:
                delta.content = str(message.content)

        if hasattr(choice, "finish_reason") and choice.finish_reason:
            delta.finish_reason = str(choice.finish_reason)

        return delta


def extract_tool_calls(message: Any) -> list[ToolCall] | None:
    """Extract tool calls from a non-streaming message."""
    if not hasattr(message, "tool_calls") or not message.tool_calls:
        return None
    return [tool_call_from_sdk(tc) for tc in message.tool_calls]
