# Architecture Overview

This document describes the architecture of the Dedalus Labs Proxy, explaining the codebase structure, request flow, and key design decisions.

## Directory Structure

```
src/dedalus_labs_proxy/
├── __init__.py          # Package initialization
├── cli.py               # CLI entry point (argparse + uvicorn)
├── config.py            # Configuration from environment variables
├── logging.py           # Structured logging setup with JSON option
├── main.py              # FastAPI app, middleware, exception handlers
├── models/              # Pydantic request/response schemas
│   ├── __init__.py
│   ├── requests.py      # ChatCompletionRequest, ChatMessage, Tool, etc.
│   └── responses.py     # ChatCompletionResponse, streaming chunks, etc.
├── routes/              # API endpoint handlers
│   ├── __init__.py      # Router exports
│   ├── chat.py          # POST /v1/chat/completions
│   ├── health.py        # GET /health, GET /health/dedalus
│   └── models.py        # GET /v1/models
└── services/            # Business logic
    ├── __init__.py
    └── dedalus.py       # Dedalus SDK wrapper (DedalusClient, DedalusRunner)
```

## Request Flow

```
                                    ┌─────────────────────────┐
                                    │    Dedalus Labs API     │
                                    │  (api.dedaluslabs.ai)   │
                                    └───────────▲─────────────┘
                                                │
                                                │ Dedalus SDK
                                                │
┌─────────────┐    ┌─────────────┐    ┌────────┴────────┐
│   Client    │───▶│  FastAPI    │───▶│  DedalusClient  │
│ (opencode,  │    │  (main.py)  │    │  (dedalus.py)   │
│  curl, etc) │◀───│             │◀───│                 │
└─────────────┘    └─────────────┘    └─────────────────┘
     │                   │
     │                   ├── Middleware: Logging, CORS
     │                   ├── Exception handlers
     │                   └── Route handlers
     │
     └── OpenAI-compatible requests/responses
```

### Detailed Flow

1. **Client Request**: Client sends OpenAI-compatible request to `/v1/chat/completions`

2. **Middleware** (main.py):
   - CORS middleware allows cross-origin requests
   - Logging middleware records request/response with timing

3. **Route Handler** (routes/chat.py):
   - Validates request using Pydantic models
   - Checks if model is supported via `config.is_valid_model()`
   - Maps model alias to Dedalus model name (e.g., `gpt-4o` → `openai/gpt-4o`)

4. **Service Layer** (services/dedalus.py):
   - `DedalusRunner.create_completion()` translates parameters
   - Calls Dedalus SDK's `AsyncDedalus.chat.completions.create()`
   - Handles both streaming and non-streaming modes

5. **Response Transformation**:
   - Dedalus SDK response is mapped to OpenAI-compatible format
   - Streaming uses Server-Sent Events (SSE) with `text/event-stream`

6. **Exception Handling**:
   - Route handlers (routes/*.py) catch SDK errors and raise `HTTPException`
   - main.py exception handlers format all errors into OpenAI-compatible JSON
   - Validation errors → 422 with `{"error": {"message", "type", "details"}}`
   - HTTP errors → `{"error": {"message": "...", "type": "..."}}`

## Key Components

### Configuration (config.py)

- Loads settings from environment variables and `.env` files
- `MODEL_MAP` provides short aliases for common models
- `Config` class validates required settings (exits if `DEDALUS_API_KEY` missing)
- Global config instance created lazily for testability

### Pydantic Models (models/)

**Request Models** (requests.py):
- `ChatCompletionRequest`: Main request body with model, messages, tools, etc.
- `ChatMessage`: Individual message with role, content, tool_calls
- `Tool`, `FunctionDefinition`: Tool/function calling schemas
- Extra fields allowed (`ConfigDict(extra="allow")`) for forward compatibility

**Response Models** (responses.py):
- `ChatCompletionResponse`: Non-streaming response
- `ChatCompletionChunk`, `ChatCompletionChunkDelta`: Streaming chunks
- `ChatCompletionUsage`: Token usage statistics

### Dedalus Service (services/dedalus.py)

**DedalusClient**: Manages the SDK client lifecycle
- Creates `AsyncDedalus` client on first use
- Provides `verify_connection()` for health checks
- Handles cleanup via `close()`

**DedalusRunner**: Executes completions
- Translates OpenAI parameters to Dedalus format
- Handles `max_tokens` vs `max_completion_tokens` based on model
- Sets default `max_tokens=16384` for tool-enabled requests

### Streaming (routes/chat.py)

- Uses `AsyncGenerator` to yield SSE-formatted chunks
- Each chunk: `data: {json}\n\n`
- Stream ends with `data: [DONE]\n\n`
- **Important**: Streaming errors are sent as SSE data events (HTTP 200 response), not as HTTP error codes. This matches OpenAI's streaming behavior where errors mid-stream are delivered as event payloads.

## Design Decisions

### OpenAI Compatibility

The proxy implements the OpenAI Chat Completions API format:
- Same request/response structure
- Same error format (`{"error": {...}}`)
- Same streaming format (SSE with `data:` prefix)

This allows clients like opencode to use the proxy without modification.

### Model Aliasing

Short model names are mapped to full Dedalus model names:

| Alias | Dedalus Model |
|-------|---------------|
| `gpt-4o` | `openai/gpt-4o` |
| `claude-3-sonnet` | `anthropic/claude-3-sonnet` |
| `gemini-1.5-pro` | `google/gemini-1.5-pro` |

Full model names (with `/`) are passed through unchanged.

### Global Client Instance

A single `DedalusClient` instance is shared across requests for connection pooling. The client is initialized lazily on first use.

### Error Handling Strategy

**Non-streaming requests** (routes catch SDK errors, raise HTTPException):
- **AuthenticationError** → 401 Unauthorized
- **APITimeoutError** → 504 Gateway Timeout (caught before APIConnectionError due to inheritance)
- **APIConnectionError** → 503 Service Unavailable
- **APIStatusError** → passes through SDK's status code

**Streaming requests** (errors emitted as SSE events):
- Errors sent as `data: {"error": {"message": "..."}}\n\n`
- HTTP response remains 200 (connection already established)
- Stream ends after error (no `[DONE]` marker)

**All responses** use OpenAI-compatible error format:
- `{"error": {"message": "...", "type": "..."}}`
- Validation errors include `details` array with field-level errors

### Logging

- Request logging includes method, path, sanitized headers
- Response logging includes status code and duration in milliseconds
- JSON output available via `--json-logs` flag for structured logging

## Testing Strategy

Tests use `httpx.AsyncClient` with `ASGITransport` for async API testing:
- Health endpoints tested directly
- Chat completions mock the Dedalus SDK
- Validation tests verify error formats
- Streaming tests verify SSE framing

See `tests/` directory for examples.
