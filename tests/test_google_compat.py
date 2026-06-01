"""Tests for Google compatibility helpers."""

from dedalus_labs_proxy.services.completion.google_compat import (
    inject_thought_signatures,
    is_google_model,
    prepare_google_request,
    sanitize_tool_schema,
    sanitize_tools_for_google,
)


def test_is_google_model() -> None:
    assert is_google_model("google/gemini-3-pro-preview")
    assert is_google_model("gemini-pro")
    assert not is_google_model("openai/gpt-4")


def test_sanitize_tool_schema_preserves_property_names() -> None:
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "maxLength": {"type": "string"},
            "name": {"type": "string", "maxLength": 10},
        },
        "additionalProperties": False,
    }
    cleaned = sanitize_tool_schema(schema)
    assert "$schema" not in cleaned
    assert "additionalProperties" not in cleaned
    assert "maxLength" in cleaned["properties"]
    assert "maxLength" not in cleaned["properties"]["name"]


def test_inject_thought_signatures_only_when_missing() -> None:
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "test", "arguments": "{}"},
                }
            ],
        }
    ]
    result = inject_thought_signatures(messages)
    assert result[0]["tool_calls"][0]["thought_signature"] is not None

    existing = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "test", "arguments": "{}"},
                    "thought_signature": "existing",
                }
            ],
        }
    ]
    preserved = inject_thought_signatures(existing)
    assert preserved[0]["tool_calls"][0]["thought_signature"] == "existing"


def test_prepare_google_request_sanitizes_tools() -> None:
    messages = [{"role": "user", "content": "hi"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search",
                "parameters": {
                    "$schema": "http://json-schema.org/draft-07/schema#",
                    "type": "object",
                    "properties": {},
                },
            },
        }
    ]
    prepared_messages, prepared_tools = prepare_google_request(
        "google/gemini-pro", messages, tools
    )
    assert prepared_messages == messages
    assert prepared_tools is not None
    assert "$schema" not in prepared_tools[0]["function"]["parameters"]


def test_sanitize_tools_for_google() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "demo",
                "parameters": {"minimum": 1, "type": "object", "properties": {}},
            },
        }
    ]
    cleaned = sanitize_tools_for_google(tools)
    assert "minimum" not in cleaned[0]["function"]["parameters"]
