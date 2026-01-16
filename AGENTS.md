# Project Operations Guide

## Build & Run

```bash
# Install dependencies
pip install -e ".[dev]"

# Run the proxy server (requires DEDALUS_API_KEY env var)
DEDALUS_API_KEY=your-key dedalus-proxy --port 8000

# Run with Docker
docker build -t dedalus-proxy .
docker run -e DEDALUS_API_KEY=your-key -p 8000:8000 dedalus-proxy
```

## Validation

Run these after implementing to get immediate feedback:

- **Tests**: `pytest tests/ -v`
- **Typecheck**: `mypy src/`
- **Lint**: `ruff check src/ tests/`

## Operational Notes

- DEDALUS_API_KEY environment variable is required; server exits with error if missing
- Default port is 8000, configurable with --port
- Log level configurable with --log-level (debug, info, warning, error)
- Use --json-logs for structured JSON log output

## Codebase Patterns

- Routes in `src/dedalus_labs_proxy/routes/`
- Pydantic models in `src/dedalus_labs_proxy/models/`
- Dedalus SDK wrapper in `src/dedalus_labs_proxy/services/dedalus.py`
- Configuration via environment variables in `src/dedalus_labs_proxy/config.py`
- FastAPI app in `src/dedalus_labs_proxy/main.py`
- CLI entry point in `src/dedalus_labs_proxy/cli.py`
