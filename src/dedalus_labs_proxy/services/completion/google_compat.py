"""Google model compatibility helpers."""

from typing import Any

from dedalus_labs_proxy.logging import logger

SKIP_THOUGHT_SIGNATURE = "c2tpcF90aG91Z2h0X3NpZ25hdHVyZV92YWxpZGF0b3I="

DISALLOWED_SCHEMA_KEYWORDS = {
    "$schema",
    "additionalProperties",
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


def is_google_model(model: str) -> bool:
    """Return True if the model is a Google/Gemini model."""
    return model.startswith("google/") or model.startswith("gemini")


def sanitize_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove JSON Schema fields that Google API rejects."""

    def _clean_dict(
        d: dict[str, Any], is_properties_dict: bool = False
    ) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for key, value in d.items():
            if not is_properties_dict and key in DISALLOWED_SCHEMA_KEYWORDS:
                continue
            if isinstance(value, dict):
                cleaned[key] = _clean_dict(
                    value, is_properties_dict=(key == "properties")
                )
            elif isinstance(value, list):
                cleaned[key] = [
                    _clean_dict(item, is_properties_dict=False)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                cleaned[key] = value
        return cleaned

    return _clean_dict(schema)


def sanitize_tools_for_google(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitize tool definitions for Google API compatibility."""
    sanitized = []
    for tool in tools:
        tool_copy = tool.copy()
        if "function" in tool_copy and "parameters" in tool_copy["function"]:
            tool_copy["function"] = tool_copy["function"].copy()
            tool_copy["function"]["parameters"] = sanitize_tool_schema(
                tool_copy["function"]["parameters"]
            )
            logger.debug(
                "Sanitized tool %s parameters",
                tool_copy["function"].get("name", "unknown"),
            )
        sanitized.append(tool_copy)
    return sanitized


def inject_thought_signatures(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inject dummy thought_signature for Gemini 3 multi-turn tool history."""
    result = []
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            msg = msg.copy()
            tool_calls = []
            for idx, tc in enumerate(msg["tool_calls"]):
                tc = tc.copy()
                if not tc.get("thought_signature") and idx == 0:
                    tc["thought_signature"] = SKIP_THOUGHT_SIGNATURE
                    logger.debug(
                        "Injected dummy thought_signature for tool call %s",
                        tc.get("function", {}).get("name", "unknown"),
                    )
                tool_calls.append(tc)
            msg["tool_calls"] = tool_calls
        result.append(msg)
    return result


def prepare_google_request(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """Apply Google-specific message and tool preparation."""
    if not is_google_model(model):
        return messages, tools

    prepared_messages = inject_thought_signatures(messages)
    prepared_tools = sanitize_tools_for_google(tools) if tools else tools
    return prepared_messages, prepared_tools
