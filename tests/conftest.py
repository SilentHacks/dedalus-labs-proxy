"""Shared test fixtures."""

import os
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import dedalus_labs
import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DEDALUS_API_KEY", "test-api-key")

from dedalus_labs_proxy.config import init_config
from dedalus_labs_proxy.dependencies import get_dedalus_client
from dedalus_labs_proxy.main import app
from dedalus_labs_proxy.services.dedalus import DedalusClient


def make_auth_error(message: str = "bad key") -> dedalus_labs.AuthenticationError:
    response = MagicMock(spec=httpx.Response)
    response.status_code = 401
    response.headers = {"x-request-id": "test-request-id"}
    return dedalus_labs.AuthenticationError(message, response=response, body=None)


def make_connection_error(
    message: str = "connection failed",
) -> dedalus_labs.APIConnectionError:
    request = MagicMock(spec=httpx.Request)
    return dedalus_labs.APIConnectionError(message=message, request=request)


def make_timeout_error() -> dedalus_labs.APITimeoutError:
    request = MagicMock(spec=httpx.Request)
    return dedalus_labs.APITimeoutError(request)


def make_status_error(
    status_code: int = 418, message: str = "bad request"
) -> dedalus_labs.APIStatusError:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.headers = {"x-request-id": "test-request-id"}
    return dedalus_labs.APIStatusError(message, response=response, body=None)


class MockMessage:
    def __init__(self, content: str, tool_calls: list[Any] | None = None) -> None:
        self.content = content
        self.role = "assistant"
        self.tool_calls = tool_calls


class MockDelta:
    def __init__(self, content: str, role: str | None = None) -> None:
        self.content = content
        self.role = role
        self.tool_calls = None


class MockChoice:
    def __init__(self, content: str, finish_reason: str = "stop") -> None:
        self.message = MockMessage(content)
        self.delta = MockDelta(content)
        self.finish_reason = finish_reason


class MockUsage:
    def __init__(self) -> None:
        self.prompt_tokens = 10
        self.completion_tokens = 5
        self.total_tokens = 15


class MockResponse:
    def __init__(
        self, content: str = "Test response", finish_reason: str = "stop"
    ) -> None:
        self.id = "chatcmpl-123"
        self.choices = [MockChoice(content, finish_reason)]
        self.usage = MockUsage()


def create_mock_dedalus_client() -> MagicMock:
    mock_runner = MagicMock()
    mock_client = MagicMock(spec=DedalusClient)
    mock_client.runner = mock_runner
    mock_client.verify_connection = AsyncMock(return_value=True)
    mock_client.list_models = AsyncMock(
        return_value=MagicMock(
            model_dump=lambda: {"object": "list", "data": [{"id": "openai/gpt-4"}]}
        )
    )
    mock_client.close = AsyncMock()

    async def mock_create_completion(*args: Any, **kwargs: Any) -> Any:
        stream = kwargs.get("stream", False)
        if stream:

            async def stream_gen() -> AsyncGenerator[MockResponse, None]:
                response = MockResponse("Hello ", "")
                response.choices[0].delta = MockDelta("Hello ", "assistant")
                response.choices[0].finish_reason = None
                yield response

                response2 = MockResponse("world!", "")
                response2.choices[0].delta = MockDelta("world!")
                response2.choices[0].finish_reason = None
                yield response2

                response3 = MockResponse("", "stop")
                response3.choices[0].delta = MockDelta("")
                response3.choices[0].finish_reason = "stop"
                yield response3

            return stream_gen()
        return MockResponse("Test response")

    mock_client.runner.create_completion = mock_create_completion
    return mock_client


@pytest.fixture
def mock_dedalus_client() -> MagicMock:
    return create_mock_dedalus_client()


@pytest.fixture
def override_dedalus_client(
    mock_dedalus_client: MagicMock,
) -> Generator[MagicMock, None, None]:
    app.dependency_overrides[get_dedalus_client] = lambda: mock_dedalus_client
    yield mock_dedalus_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client(
    override_dedalus_client: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    init_config(require_api_key=True)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
