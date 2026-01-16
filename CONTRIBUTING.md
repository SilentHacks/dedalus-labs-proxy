# Contributing to Dedalus Labs Proxy

Thank you for your interest in contributing! This guide will help you set up your development environment and understand our contribution process.

## Development Setup

### Prerequisites

- Python 3.11+
- Git

### Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd dedalus-labs-proxy
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install the package in development mode with dev dependencies:

```bash
pip install -e ".[dev]"
```

This installs:
- The package in editable mode (`-e`)
- Development tools: pytest, black, ruff, mypy, httpx

### Running the Server Locally

```bash
export DEDALUS_API_KEY=your-api-key
dedalus-proxy --log-level debug
```

Or create a `.env` file in the project root:

```
DEDALUS_API_KEY=your-api-key
```

For development with auto-reload:

```bash
uvicorn dedalus_labs_proxy.main:app --reload --port 8000
```

**Note:** Never commit API keys or `.env` files to version control.

## Validation Commands

Always run these before submitting a PR:

```bash
# Run all tests
pytest tests/ -v

# Type checking
mypy src/

# Linting
ruff check src/ tests/
```

All three must pass for a PR to be accepted.

### Auto-fixing Lint Issues

```bash
# Fix auto-fixable lint issues
ruff check --fix src/ tests/

# Format code with black
black src/ tests/
```

## Code Style

We use the following tools:

| Tool | Purpose | Configuration |
|------|---------|---------------|
| **ruff** | Linting (E, F, W, I, N, B, C90, UP rules) | `pyproject.toml` |
| **black** | Code formatting | Line length 88, Python 3.11+ |
| **mypy** | Type checking (with strict options) | `pyproject.toml` |

### Style Guidelines

- All functions must have type annotations
- Follow PEP 8 naming conventions
- Keep functions focused and testable
- Add docstrings for public APIs

## Project Structure

```
src/dedalus_labs_proxy/
├── cli.py           # CLI entry point (argparse)
├── config.py        # Configuration from environment
├── logging.py       # Structured logging setup
├── main.py          # FastAPI app initialization
├── models/          # Pydantic request/response models
│   ├── requests.py
│   └── responses.py
├── routes/          # API route handlers
│   ├── chat.py      # /v1/chat/completions
│   ├── health.py    # /health endpoints
│   └── models.py    # /v1/models
└── services/        # Business logic
    └── dedalus.py   # Dedalus SDK wrapper
```

## Pull Request Process

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the code style guidelines

3. **Run validation** to ensure all checks pass:
   ```bash
   pytest tests/ -v && mypy src/ && ruff check src/ tests/
   ```

4. **Commit** with a descriptive message:
   ```bash
   git commit -m "feat: add support for new model type"
   ```

   Follow conventional commits when possible:
   - `feat:` new feature
   - `fix:` bug fix
   - `docs:` documentation changes
   - `refactor:` code refactoring
   - `test:` adding/updating tests

5. **Push and create a PR** with:
   - Clear description of what changed
   - Any related issue numbers
   - Screenshots for UI changes (if applicable)

## Testing

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_chat.py -v

# Specific test
pytest tests/test_chat.py::test_chat_completions_success -v
```

### Writing Tests

- Tests live in the `tests/` directory
- Use pytest and pytest-asyncio for async tests
- Use httpx with `ASGITransport` for async API testing
- Mock external services (Dedalus SDK) in tests
- Tests don't require a real API key (they mock the Dedalus SDK)

Example test structure:

```python
import pytest
from httpx import ASGITransport, AsyncClient
from dedalus_labs_proxy.main import app

@pytest.mark.asyncio
async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
```

## Need Help?

- Check existing issues for similar questions
- Review the [API Overview](docs/api-overview.md) for endpoint documentation
- Look at existing code for patterns and conventions
