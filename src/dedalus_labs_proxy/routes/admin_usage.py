"""Admin endpoints for usage observability."""

from dataclasses import asdict
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from dedalus_labs_proxy.auth import (
    INVALID_API_KEY_MESSAGE,
    MISSING_API_KEY_MESSAGE,
    extract_bearer_token,
    validate_admin_auth,
)
from dedalus_labs_proxy.config import get_config
from dedalus_labs_proxy.usage.bootstrap import ensure_usage_tracking
from dedalus_labs_proxy.usage.models import SessionDetail, UsageSummary
from dedalus_labs_proxy.usage.store import UsageStore
from dedalus_labs_proxy.usage.tracker import parse_session_id

router = APIRouter()


def require_admin_auth(request: Request) -> None:
    """Ensure the caller presents a valid admin API key."""
    config = get_config()
    if not config.usage_admin_enabled or not config.usage_tracking:
        raise HTTPException(status_code=404, detail="Not found")
    if validate_admin_auth(request, config.usage_admin_keys) is not None:
        token = extract_bearer_token(request.headers.get("authorization"))
        detail = (
            MISSING_API_KEY_MESSAGE if token is None else INVALID_API_KEY_MESSAGE
        )
        raise HTTPException(status_code=401, detail=detail)


def get_usage_store(request: Request) -> UsageStore:
    """Return the shared usage store from application state."""
    ensure_usage_tracking(request.app)
    store = getattr(request.app.state, "usage_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Usage tracking is not enabled")
    return cast(UsageStore, store)


def _serialize_summary(summary: UsageSummary) -> dict[str, Any]:
    return {
        "period": summary.period,
        "total_requests": summary.total_requests,
        "total_tokens": summary.total_tokens,
        "store_scope": "per_process_in_memory",
        "by_model": {
            model: asdict(stats) for model, stats in summary.by_model.items()
        },
        "by_client": {
            client: asdict(stats) for client, stats in summary.by_client.items()
        },
    }


def _serialize_session(detail: SessionDetail) -> dict[str, Any]:
    return {
        "session": asdict(detail.session),
        "recent_requests": [asdict(record) for record in detail.recent_requests],
        "recent_requests_retained": len(detail.recent_requests),
        "recent_requests_note": (
            "recent_requests only includes records still present in the "
            "in-memory ring buffer; session totals cover all recorded requests"
        ),
    }


@router.get("/v1/admin/usage", dependencies=[Depends(require_admin_auth)])
async def get_usage_summary(
    store: UsageStore = Depends(get_usage_store),
) -> dict[str, Any]:
    """Return in-memory usage aggregates."""
    summary = await store.get_summary()
    return _serialize_summary(summary)


@router.get(
    "/v1/admin/sessions/{session_id}",
    dependencies=[Depends(require_admin_auth)],
)
async def get_session_usage(
    session_id: str,
    store: UsageStore = Depends(get_usage_store),
) -> dict[str, Any]:
    """Return usage rollup for a tracked session."""
    validated_session_id = parse_session_id(session_id)
    if validated_session_id is None:
        raise HTTPException(status_code=400, detail="Invalid session id")
    detail = await store.get_session(validated_session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _serialize_session(detail)
