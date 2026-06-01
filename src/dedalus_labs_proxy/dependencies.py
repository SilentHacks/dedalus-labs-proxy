"""FastAPI dependency providers."""

from fastapi import Request

from dedalus_labs_proxy.services.dedalus import DedalusClient


def get_dedalus_client(request: Request) -> DedalusClient:
    """Return the shared Dedalus client from application state."""
    return request.app.state.dedalus_client
