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

### Example Request

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Streaming

```bash
curl -N http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
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

## Supported Models

Models are mapped to Dedalus Labs equivalents:

- `gpt-4`, `gpt-4-turbo`, `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo`
- `claude-3-opus`, `claude-3-sonnet`, `claude-3-haiku`
- `gemini-1.5-pro`, `gemini-1.5-flash`

You can also use full model names like `openai/gpt-4o` or `anthropic/claude-3-sonnet`.

## Documentation

- [opencode Integration Guide](docs/opencode-integration.md) - Configure opencode with this proxy
- [API Overview](docs/api-overview.md) - Detailed endpoint documentation
- [Architecture](docs/architecture.md) - Codebase structure and design
- [Contributing](CONTRIBUTING.md) - Development setup and guidelines

## License

MIT
