"""Pydantic models for API responses."""

from typing import Any

from pydantic import BaseModel


class FunctionCall(BaseModel):
    """Function call in a tool call."""

    name: str
    arguments: str


class ToolCall(BaseModel):
    """Tool call from the model."""

    id: str
    type: str = "function"
    function: FunctionCall
    thought_signature: str | None = None


class ToolCallDelta(BaseModel):
    """Tool call delta in streaming responses."""

    index: int
    id: str | None = None
    type: str | None = None
    function: dict[str, Any] | None = None
    thought_signature: str | None = None


class ChatMessageResponse(BaseModel):
    """Chat message in a response."""

    role: str
    content: str | None = None
    tool_calls: list[ToolCall] | None = None


class ChatCompletionResponseChoice(BaseModel):
    """Choice in a chat completion response."""

    index: int
    message: ChatMessageResponse
    finish_reason: str | None


class ChatCompletionUsage(BaseModel):
    """Token usage information."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """Non-streaming chat completion response."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionResponseChoice]
    usage: ChatCompletionUsage


class ChatCompletionChunkDelta(BaseModel):
    """Delta in a streaming chunk."""

    role: str | None = None
    content: str | None = None
    tool_calls: list[ToolCallDelta] | None = None


class ChatCompletionChunkChoice(BaseModel):
    """Choice in a streaming chunk."""

    index: int
    delta: ChatCompletionChunkDelta
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    """Streaming chat completion chunk."""

    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[ChatCompletionChunkChoice]
