"""Pydantic models for API requests."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FunctionDefinition(BaseModel):
    """Function definition for tool calls."""

    name: str
    description: str | None = None
    parameters: dict[str, Any] | None = None
    strict: bool | None = None


class Tool(BaseModel):
    """Tool definition."""

    type: str = "function"
    function: FunctionDefinition


class ToolChoiceFunction(BaseModel):
    """Function specification for tool_choice."""

    name: str


class ToolChoiceObject(BaseModel):
    """Object form of tool_choice."""

    type: str = "function"
    function: ToolChoiceFunction


class ContentPart(BaseModel):
    """Content part for multi-modal messages."""

    model_config = ConfigDict(extra="allow")

    type: str
    text: str | None = None
    image_url: dict[str, Any] | None = None


class ChatMessage(BaseModel):
    """Chat message in a conversation."""

    model_config = ConfigDict(extra="allow")

    role: str
    content: str | list[ContentPart] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    """Request body for chat completions."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    top_p: float | None = None
    stop: str | list[str] | None = None
    tools: list[Tool] | None = None
    tool_choice: str | ToolChoiceObject | None = None
    parallel_tool_calls: bool | None = None
    # OpenCode variant fields mapped to Dedalus API
    reasoning_effort: str | None = Field(
        default=None, alias="reasoningEffort"
    )  # "low", "medium", "high"
    verbosity: str | None = Field(
        default=None, alias="textVerbosity"
    )  # "low", "medium", "high"
