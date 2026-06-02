"""FastAPI dependency providers."""

from typing import cast

from fastapi import Request

from dedalus_labs_proxy.services.dedalus import DedalusClient
from dedalus_labs_proxy.usage.bootstrap import ensure_usage_tracking
from dedalus_labs_proxy.usage.models import UsageContext
from dedalus_labs_proxy.usage.tracker import UsageTracker


def get_dedalus_client(request: Request) -> DedalusClient:
    """Return the shared Dedalus client from application state."""
    return cast(DedalusClient, request.app.state.dedalus_client)


def get_usage_tracker(request: Request) -> UsageTracker | None:
    """Return the shared usage tracker when tracking is enabled."""
    ensure_usage_tracking(request.app)
    return getattr(request.app.state, "usage_tracker", None)


def maybe_begin_usage(
    request: Request,
    chat_request: object,
) -> UsageContext | None:
    """Begin usage tracking for a chat completion request, if enabled."""
    tracker = get_usage_tracker(request)
    if tracker is None:
        return None
    from dedalus_labs_proxy.models.requests import ChatCompletionRequest

    if not isinstance(chat_request, ChatCompletionRequest):
        return None
    return tracker.begin(request=request, chat_request=chat_request)
