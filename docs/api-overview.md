# API Overview

This document provides an overview of the endpoints exposed by the Dedalus Labs Proxy. The proxy implements the OpenAI chat completions API, allowing you to use the official `openai` Python library or any OpenAI-compatible client for chat workflows.

## Interactive Documentation

The proxy includes auto-generated interactive API documentation:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Endpoints

### GET /health

Fast local health check that verifies the proxy server is running.

**Response:**
```json
{"status": "ok"}
```

### GET /health/dedalus

Verifies connectivity to the Dedalus Labs API upstream service.

**Response (success):**
```json
{
  "status": "ok",
  "service": "dedalus-api",
  "message": "API connection verified"
}
```

**Response (failure):**
- `401 Unauthorized` — Invalid or missing `DEDALUS_API_KEY`
- `503 Service Unavailable` — Cannot connect to Dedalus API

### GET /v1/models

Returns an empty model list. Users should pass model names directly as expected
by the Dedalus Labs API (e.g., `openai/gpt-4o`, `anthropic/claude-3-sonnet`).

**Response:**
```json
{
  "object": "list",
  "data": []
}
```

### POST /v1/chat/completions

The main endpoint for generating chat completions. Supports both non-streaming and streaming modes.

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | Yes | Model ID (from `/v1/models`) |
| `messages` | array | Yes | Conversation history |
| `stream` | boolean | No | Enable streaming (default: `false`) |
| `temperature` | float | No | Sampling temperature (0-2) |
| `max_tokens` | integer | No | Maximum tokens to generate |
| `max_completion_tokens` | integer | No | Alternative to `max_tokens` |
| `top_p` | float | No | Nucleus sampling parameter |
| `stop` | string/array | No | Stop sequences |
| `tools` | array | No | Function/tool definitions |
| `tool_choice` | string/object | No | Tool selection: `"auto"`, `"none"`, `"required"`, or `{"type": "function", "function": {"name": "..."}}` |
| `parallel_tool_calls` | boolean | No | Allow parallel tool calls |
| `reasoningEffort` | string | No | Reasoning depth: `low`, `medium`, `high` |
| `textVerbosity` | string | No | Response verbosity: `low`, `medium`, `high` |

#### Message Format

Basic text message:
```json
{
  "role": "user",
  "content": "Hello, world!"
}
```

Supported roles: `system`, `user`, `assistant`, `tool`

**Message fields:**

| Field | Type | Description |
|-------|------|-------------|
| `role` | string | Message role (`system`, `user`, `assistant`, `tool`) |
| `content` | string or array | Text content, or array of content parts for multimodal |
| `name` | string | Optional name for the message author |
| `tool_calls` | array | Tool calls made by assistant (for `role: assistant`) |
| `tool_call_id` | string | ID of the tool call being responded to (for `role: tool`) |

**Multimodal content (array format):**
```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "What's in this image?"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
  ]
}
```

**Tool response message:**
```json
{
  "role": "tool",
  "tool_call_id": "call_abc123",
  "content": "{\"temperature\": 22, \"unit\": \"celsius\"}"
}
```

#### Non-Streaming Response

When `stream: false` (default):

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1704067200,
  "model": "claude-sonnet-4-20250514",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 15,
    "total_tokens": 25
  }
}
```

#### Streaming Response

When `stream: true`, the endpoint returns Server-Sent Events (SSE) with `Content-Type: text/event-stream`.

Each event is prefixed with `data: ` followed by a JSON chunk:

```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1704067200,"model":"claude-sonnet-4-20250514","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1704067200,"model":"claude-sonnet-4-20250514","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1704067200,"model":"claude-sonnet-4-20250514","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1704067200,"model":"claude-sonnet-4-20250514","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

**Key streaming details:**
- Each chunk contains a `delta` object with incremental content
- The stream ends with `data: [DONE]`
- Use `curl -N` to disable buffering when testing

#### Tool Calling

The proxy supports function/tool calling. Define tools in your request:

```json
{
  "model": "claude-sonnet-4-20250514",
  "messages": [{"role": "user", "content": "What's the weather in Paris?"}],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string"}
          },
          "required": ["location"]
        }
      }
    }
  ]
}
```

When the model decides to call a tool, the response includes `tool_calls`:

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_abc123",
            "type": "function",
            "function": {
              "name": "get_weather",
              "arguments": "{\"location\": \"Paris\"}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ]
}
```

## Error Responses

All errors follow an OpenAI-compatible format:

```json
{
  "error": {
    "message": "Error description",
    "type": "error_type"
  }
}
```

**Error types by status code:**

| Status | Type | Example |
|--------|------|---------|
| `400 Bad Request` | `http_error` | `{"error": {"message": "Model 'unknown' not supported", "type": "http_error"}}` |
| `401 Unauthorized` | `authentication_error` | `{"error": {"message": "Authentication failed: Invalid API key", "type": "authentication_error"}}` |
| `422 Unprocessable Entity` | `validation_error` | `{"error": {"message": "Invalid request data", "type": "validation_error", "details": [...]}}` |
| `500 Internal Server Error` | `internal_error` | `{"error": {"message": "Internal server error", "type": "internal_error"}}` |
| `503 Service Unavailable` | `http_error` | `{"error": {"message": "Cannot connect to Dedalus API", "type": "http_error"}}` |
| `504 Gateway Timeout` | `http_error` | `{"error": {"message": "Request timed out...", "type": "http_error"}}` |

**Streaming errors:**

During streaming, errors are sent as SSE data events:
```
data: {"error": {"message": "Authentication failed: Invalid API key"}}
```

## Using with OpenAI Python Library

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-used"  # Authentication handled by proxy
)

response = client.chat.completions.create(
    model="claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": "Hello!"}]
)

print(response.choices[0].message.content)
```

For streaming:

```python
stream = client.chat.completions.create(
    model="claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

## curl Examples

**Non-streaming:**
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-20250514",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

**Streaming (use -N to disable buffering):**
```bash
curl -N http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-20250514",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'
```
