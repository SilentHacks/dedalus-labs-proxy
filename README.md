# Dedalus Labs Proxy

OpenAI-compatible proxy server for the Dedalus Labs API. Use your favorite OpenAI-compatible tools (like [opencode](https://opencode.ai)) with Dedalus Labs models.

## Prerequisites

- Python 3.11+
- `DEDALUS_API_KEY` environment variable

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
# Set your API key first
export DEDALUS_API_KEY=your-api-key

docker compose up
```

Or create a `.env` file with `DEDALUS_API_KEY=your-api-key`.

## Usage

Start the proxy server:

```bash
export DEDALUS_API_KEY=your-api-key
dedalus-proxy
```

The server runs on `http://localhost:8000` by default.

### CLI Options

```
--port PORT        Port to run the server on (default: 8000)
--host HOST        Host to bind to (default: localhost)
--log-level LEVEL  Log level: debug, info, warning, error (default: info)
--json-logs        Output logs in JSON format
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEDALUS_API_KEY` | (required) | Your Dedalus Labs API key |
| `REQUEST_TIMEOUT` | `300` | Request timeout in seconds |
| `MAX_RETRIES` | `2` | Maximum retry attempts for failed requests |
| `STREAM_KEEPALIVE_INTERVAL` | `15` | Seconds between keepalive pings during streaming |
| `TOOL_MAX_TOKENS` | `128000` | Default max tokens for tool-enabled requests |

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
| `GET /health` | Fast local health check |
| `GET /health/dedalus` | Verify Dedalus API connection and auth |
| `GET /v1/models` | List available models |
| `POST /v1/chat/completions` | Chat completions (streaming and non-streaming) |

Interactive API documentation is available at `/docs` when the server is running.

## Model Names

Pass model names directly as expected by the Dedalus Labs API. Examples:

- `openai/gpt-5.2`, `openai/gpt-4.1`, `openai/gpt-4o`
- `anthropic/claude-opus-4-5`, `anthropic/claude-sonnet-4-5`
- `google/gemini-3-pro-preview`, `google/gemini-2.5-pro`

See Dedalus Labs documentation for the full list of available models.

### Tested with opencode

The following models have been verified to work with [opencode](https://opencode.ai):

| Model | Status |
|-------|--------|
| `anthropic/claude-opus-4-5` | Working |
| `openai/gpt-5.2` | Working |
| `google/gemini-3-pro-preview` | Partial - [known issues with multi-turn tool calling](docs/GOOGLE_TOOL_CALLING_BUG.md) |

Other models may or may not work. See the [opencode integration guide](docs/opencode-integration.md) for configuration details.

## Documentation

- [opencode Integration Guide](docs/opencode-integration.md) - Configure opencode with this proxy
- [API Overview](docs/api-overview.md) - Detailed endpoint documentation
- [Architecture](docs/architecture.md) - Codebase structure and design
- [Contributing](CONTRIBUTING.md) - Development setup and guidelines

## License

MIT
