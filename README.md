# Dedalus Labs Proxy

[![CI](https://github.com/SilentHacks/dedalus-labs-proxy/actions/workflows/ci.yml/badge.svg)](https://github.com/SilentHacks/dedalus-labs-proxy/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

OpenAI-compatible proxy server for the [Dedalus Labs](https://www.dedaluslabs.ai) API. Use your favorite OpenAI-compatible tools (like [OpenCode](https://opencode.ai)) with Dedalus Labs models.

## Features

- OpenAI-compatible `/v1/chat/completions` and `/v1/models` endpoints
- Streaming SSE with keepalive pings for long-running tool calls
- Google Gemini compatibility workarounds (tool schemas, thought signatures)
- Docker and Docker Compose support
- Configurable via environment variables or CLI flags

## Prerequisites

- Python 3.11+
- `DEDALUS_API_KEY` environment variable ([get your API key here](https://www.dedaluslabs.ai/dashboard/api-keys))

## Quick Start

```bash
git clone https://github.com/SilentHacks/dedalus-labs-proxy.git
cd dedalus-labs-proxy
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env       # then edit .env with your API key
dedalus-proxy
```

The server runs at `http://localhost:8000` by default.

## Installation

### pip

```bash
pip install .

# Or for development
pip install -e ".[dev]"
```

### Docker

```bash
docker build -t dedalus-proxy .
docker run -e DEDALUS_API_KEY=your-key -p 8000:8000 dedalus-proxy
```

### Docker Compose

```bash
export DEDALUS_API_KEY=your-api-key
docker compose up
```

Or create a `.env` file with `DEDALUS_API_KEY=your-api-key`.

## Usage

```bash
export DEDALUS_API_KEY=your-api-key
dedalus-proxy
```

### CLI Options

```
--port PORT        Port to run the server on (default: 8000, env PORT)
--host HOST        Host to bind to (default: localhost, env HOST)
--log-level LEVEL  Log level: debug, info, warning, error (default: info)
--json-logs        Output logs in JSON format
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEDALUS_API_KEY` | (required) | Your Dedalus Labs API key |
| `HOST` | `localhost` | Host to bind (overridden by `--host`) |
| `PORT` | `8000` | Port to bind (overridden by `--port`) |
| `LOG_LEVEL` | `INFO` | Default log level (overridden by `--log-level`) |
| `MAX_TOKENS` | `4096` | Server default when request omits max tokens |
| `DEFAULT_TEMPERATURE` | `0.7` | Server default when request omits temperature |
| `REQUEST_TIMEOUT` | `300` | Request timeout in seconds |
| `MAX_RETRIES` | `2` | Maximum retry attempts for failed requests |
| `STREAM_KEEPALIVE_INTERVAL` | `15` | Seconds between keepalive pings during streaming |
| `TOOL_MAX_TOKENS` | `128000` | Default max tokens for tool-enabled requests (large values increase cost and latency) |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins, or `*` for all |
| `DISABLE_DOCS` | `false` | Set to `true` to disable `/docs` and `/redoc` |
| `PROXY_API_KEYS` | (unset) | Comma-separated client API keys; when set, requires `Authorization: Bearer <key>` |

See [`.env.example`](.env.example) for a full template.

### Example Request

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-4o",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Streaming

```bash
curl -N http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-4o",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'
```

Note: The `-N` flag disables buffering for real-time streaming output.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Fast local health check (use this for orchestrator probes) |
| `GET /health/dedalus` | Verify Dedalus API auth via `models.list` (no completion token cost) |
| `GET /v1/models` | List available models from Dedalus Labs API |
| `POST /v1/chat/completions` | Chat completions (streaming and non-streaming) |

Interactive API documentation is available at `/docs` when the server is running.

## Model Names

Pass model names directly as expected by the Dedalus Labs API. Examples:

- `openai/gpt-5.2`, `openai/gpt-4.1`, `openai/gpt-4o`
- `anthropic/claude-opus-4-5`, `anthropic/claude-sonnet-4-5`
- `google/gemini-3-pro-preview`, `google/gemini-3-flash-preview`

Run `curl http://localhost:8000/v1/models` to list models available to your API key.

### Tested with OpenCode

The following models have been verified to work with [OpenCode](https://opencode.ai):

| Model | Status |
|-------|--------|
| `anthropic/claude-opus-4-5` | Working |
| `openai/gpt-5.2` | Working |
| `google/gemini-3-pro-preview` | Working (see [notes](docs/GOOGLE_TOOL_CALLING_BUG.md)) |

Other models may or may not work. See the [OpenCode integration guide](docs/opencode-integration.md) for configuration details.

## Security

By default, this proxy has **no client authentication**. Anyone who can reach the server can use your `DEDALUS_API_KEY` and incur API charges.

To restrict access when exposing the proxy beyond trusted networks, set `PROXY_API_KEYS` to a comma-separated list of client keys:

```bash
export PROXY_API_KEYS=dev-key-1,dev-key-2
```

Clients must then send `Authorization: Bearer <key>`. OpenAI-compatible SDKs (including OpenCode) support this via their `api_key` option — use a proxy key, not your Dedalus key. When unset, behavior is unchanged.

- `GET /health` remains unauthenticated so Docker and load balancer probes keep working.
- All other endpoints (including `/v1/*` and `/health/dedalus`) require a valid proxy key when `PROXY_API_KEYS` is set.

Additional hardening:

- The CLI binds to `localhost` by default. Docker binds to `0.0.0.0`.
- Do not expose the proxy on a public network without authentication or a reverse proxy in front.
- CORS defaults to `*` (all origins). Restrict with `CORS_ORIGINS` in production.
- Use `GET /health` for load balancer and container probes, not `/health/dedalus`.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
mypy src/
ruff check src/ tests/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor guide.

## Documentation

- [OpenCode Integration Guide](docs/opencode-integration.md) - Configure OpenCode with this proxy
- [API Overview](docs/api-overview.md) - Detailed endpoint documentation
- [Architecture](docs/architecture.md) - Codebase structure and design
- [Contributing](CONTRIBUTING.md) - Development setup and guidelines

## License

This project is licensed under the [MIT License](LICENSE).

## Disclaimer

This is an unofficial community proxy for [Dedalus Labs](https://www.dedaluslabs.ai). It is not affiliated with or endorsed by Dedalus Labs.
