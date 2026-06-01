"""Tests for Dedalus error mapping."""

import pytest
from fastapi import HTTPException

from dedalus_labs_proxy.services.completion.errors import (
    dedalus_error_payload,
    map_dedalus_exception_to_http,
)
from dedalus_labs_proxy.services.completion.sse import yield_sse_error
from tests.conftest import (
    make_auth_error,
    make_connection_error,
    make_status_error,
    make_timeout_error,
)


@pytest.mark.asyncio
async def test_yield_sse_error_includes_done() -> None:
    events = [event async for event in yield_sse_error({"error": {"message": "fail"}})]
    assert any("fail" in event for event in events)
    assert events[-1] == "data: [DONE]\n\n"


def test_map_authentication_error() -> None:
    exc = map_dedalus_exception_to_http(make_auth_error())
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 401


def test_map_timeout_error() -> None:
    exc = map_dedalus_exception_to_http(make_timeout_error())
    assert exc.status_code == 504


def test_map_connection_error() -> None:
    exc = map_dedalus_exception_to_http(make_connection_error())
    assert exc.status_code == 503


def test_map_status_error() -> None:
    http_exc = map_dedalus_exception_to_http(make_status_error(status_code=418))
    assert http_exc.status_code == 418


def test_dedalus_error_payload_auth() -> None:
    payload = dedalus_error_payload(make_auth_error())
    assert "Authentication failed" in payload["error"]["message"]
