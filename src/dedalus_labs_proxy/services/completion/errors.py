"""Dedalus SDK error mapping."""

from collections.abc import AsyncGenerator
from typing import Any

import dedalus_labs
from fastapi import HTTPException

from dedalus_labs_proxy.services.completion.sse import yield_sse_error


def dedalus_error_payload(exc: Exception) -> dict[str, Any]:
    """Map a Dedalus SDK exception to an OpenAI-compatible error payload."""
    if isinstance(exc, dedalus_labs.AuthenticationError):
        return {"error": {"message": "Authentication failed: Invalid API key"}}
    if isinstance(exc, dedalus_labs.APITimeoutError):
        return {
            "error": {
                "message": (
                    "Request timed out. Try reducing the complexity of your query."
                )
            }
        }
    if isinstance(exc, dedalus_labs.APIConnectionError):
        return {
            "error": {"message": f"Failed to connect to Dedalus API: {exc!s}"}
        }
    if isinstance(exc, dedalus_labs.APIStatusError):
        return {"error": {"message": exc.message, "code": str(exc.status_code)}}
    return {"error": {"message": "Internal server error", "type": "internal_error"}}


def map_dedalus_exception_to_http(exc: Exception) -> HTTPException:
    """Map a Dedalus SDK exception to an HTTPException."""
    if isinstance(exc, dedalus_labs.AuthenticationError):
        return HTTPException(
            status_code=401, detail="Authentication failed: Invalid API key"
        )
    if isinstance(exc, dedalus_labs.APITimeoutError):
        return HTTPException(
            status_code=504,
            detail="Request timed out. Try reducing the complexity of your query.",
        )
    if isinstance(exc, dedalus_labs.APIConnectionError):
        return HTTPException(
            status_code=503, detail=f"Failed to connect to Dedalus API: {exc!s}"
        )
    if isinstance(exc, dedalus_labs.APIStatusError):
        return HTTPException(status_code=exc.status_code, detail=exc.message)
    return HTTPException(status_code=500, detail="Internal server error")


async def stream_dedalus_errors(exc: Exception) -> AsyncGenerator[str, None]:
    """Yield SSE error events for a Dedalus SDK exception."""
    async for event in yield_sse_error(dedalus_error_payload(exc)):
        yield event
