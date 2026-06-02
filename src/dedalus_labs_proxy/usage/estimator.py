"""Heuristic context size estimation."""

from typing import Any

import orjson

MESSAGE_OVERHEAD_TOKENS = 4


def estimate_context_tokens(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    chars_per_token: int = 4,
) -> int:
    """Estimate input token count from messages and tool definitions."""
    if chars_per_token <= 0:
        chars_per_token = 4

    payload: dict[str, Any] = {"messages": messages}
    if tools:
        payload["tools"] = tools

    char_count = len(orjson.dumps(payload))
    token_estimate = char_count // chars_per_token
    token_estimate += MESSAGE_OVERHEAD_TOKENS * len(messages)
    return max(token_estimate, 0)
