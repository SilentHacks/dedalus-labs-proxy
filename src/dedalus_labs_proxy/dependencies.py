"""FastAPI dependency providers."""

from typing import cast

from fastapi import Request

from dedalus_labs_proxy.services.dedalus import DedalusClient


def get_dedalus_client(request: Request) -> DedalusClient:
    """Return the shared Dedalus client from application state."""
    return cast(DedalusClient, request.app.state.dedalus_client)
