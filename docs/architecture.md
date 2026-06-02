# Architecture Overview

This document describes the architecture of the Dedalus Labs Proxy, explaining the codebase structure, request flow, and key design decisions.

## Directory Structure

```
src/dedalus_labs_proxy/
├── __init__.py          # Package initialization
├── cli.py               # CLI entry point (argparse + uvicorn)
├── config.py            # Configuration from environment variables
├── auth.py              # Optional client bearer-token authentication
├── dependencies.py      # FastAPI dependency providers
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
    ├── dedalus.py       # Dedalus SDK wrapper (DedalusClient, DedalusRunner)
    └── completion/      # Chat completion orchestration
        ├── adapters.py          # SDK chunk → OpenAI delta mapping
        ├── errors.py            # Dedalus exception → HTTP/SSE errors
        ├── google_compat.py     # Gemini tool/schema workarounds
        ├── service.py           # ChatCompletionService
        ├── sse.py               # SSE formatting helpers
        └── streaming_keepalive.py
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
│   Client    │───▶│  FastAPI    │───▶│ ChatCompletion  │
│ (OpenCode,  │    │  (main.py)  │    │    Service      │
│  curl, etc) │◀───│             │◀───│                 │
└─────────────┘    └─────────────┘    └────────┬────────┘
     │                   │                     │
     │                   │                     └── DedalusClient
     │                   ├── Middleware: CORS, proxy auth, logging
     │                   ├── Exception handlers
     │                   └── Route handlers (thin)
     │
     └── OpenAI-compatible requests/responses
```

### Detailed Flow

1. **Client Request**: Client sends OpenAI-compatible request to `/v1/chat/completions`

2. **Middleware** (main.py):
   - CORS middleware (configurable via `CORS_ORIGINS`)
   - Proxy auth middleware (optional, via `PROXY_API_KEYS`; exempts `GET /health` and `OPTIONS`)
   - Logging middleware records request/response with timing

3. **Route Handler** (routes/chat.py):
   - Validates request using Pydantic models
   - Delegates to `ChatCompletionService`

4. **Completion Service** (services/completion/service.py):
   - Applies server defaults, Google compatibility, and tool preparation
   - Calls `DedalusRunner.create_completion()` via injected `DedalusClient`

5. **Response Transformation**:
   - Dedalus SDK response is mapped to OpenAI-compatible format via adapters
   - Streaming uses Server-Sent Events (SSE) with `text/event-stream`

6. **Exception Handling**:
   - Non-streaming: service raises `HTTPException` mapped from SDK errors
   - Streaming: errors emitted as SSE data events at HTTP 200, followed by `[DONE]`
   - Validation errors → 422 with OpenAI-compatible JSON

## Key Components

### Configuration (config.py)

- Loads settings from environment variables and `.env` files
- `ConfigurationError` raised when required settings are missing
- `init_config()` used at startup (CLI and FastAPI lifespan)

### ChatCompletionService (services/completion/service.py)

Orchestrates non-streaming, default streaming, and Google+tools simulated streaming paths through a single `prepare_request()` pipeline.

### Dedalus Service (services/dedalus.py)

**DedalusClient**: Manages SDK client lifecycle, injected via FastAPI dependencies.

**DedalusRunner**: Executes completions with model-family-specific token parameter handling.

### Streaming (services/completion/sse.py)

- Each chunk: `data: {json}\n\n`
- Stream ends with `data: [DONE]\n\n`
- Errors mid-stream: HTTP 200 with error JSON in SSE body, then `[DONE]`

## Design Decisions

### OpenAI Compatibility

The proxy implements the OpenAI Chat Completions API format:
- Same request/response structure
- Same error format (`{"error": {...}}`)
- Same streaming format (SSE with `data:` prefix)

### Dependency Injection

`DedalusClient` is stored on `app.state` during lifespan and injected into routes via `get_dedalus_client`. Tests override the dependency instead of patching module globals.

### Error Handling Strategy

**Non-streaming requests**:
- **AuthenticationError** → 401 Unauthorized
- **APITimeoutError** → 504 Gateway Timeout
- **APIConnectionError** → 503 Service Unavailable
- **APIStatusError** → passes through SDK's status code
- Empty upstream `choices` → 502 Bad Gateway

**Streaming requests**:
- Errors sent as `data: {"error": {"message": "..."}}\n\n`
- HTTP response remains 200 (connection already established)
- Stream always ends with `[DONE]` after success or error

### Security

- Optional client authentication via `PROXY_API_KEYS` (comma-separated bearer tokens); disabled when unset
- When enabled, `GET /health` and `OPTIONS` remain exempt for orchestrator probes and CORS preflight
- The server's `DEDALUS_API_KEY` is used upstream; client keys only gate access to the proxy
- Default bind is `localhost`; Docker uses `0.0.0.0`
- Use `/health` for probes; `/health/dedalus` calls `models.list` (no completion token cost)

## Testing Strategy

Tests use `httpx.AsyncClient` with `ASGITransport` and `app.dependency_overrides` for mocking:
- Health endpoints tested directly
- Chat completions mock the Dedalus client dependency
- Unit tests cover Google compat, error mapping, and token kwargs

See `tests/` directory for examples.
