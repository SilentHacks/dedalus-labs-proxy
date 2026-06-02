"""Admin endpoints for usage observability."""

from dataclasses import asdict
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from dedalus_labs_proxy.usage.models import SessionDetail, UsageSummary
from dedalus_labs_proxy.usage.store import UsageStore

router = APIRouter()


def get_usage_store(request: Request) -> UsageStore:
    """Return the shared usage store from application state."""
    store = getattr(request.app.state, "usage_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Usage tracking is not enabled")
    return cast(UsageStore, store)


def _serialize_summary(summary: UsageSummary) -> dict[str, Any]:
    return {
        "period": summary.period,
        "total_requests": summary.total_requests,
        "total_tokens": summary.total_tokens,
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
    }


@router.get("/v1/admin/usage")
async def get_usage_summary(
    store: UsageStore = Depends(get_usage_store),
) -> dict[str, Any]:
    """Return in-memory usage aggregates."""
    summary = await store.get_summary()
    return _serialize_summary(summary)


@router.get("/v1/admin/sessions/{session_id}")
async def get_session_usage(
    session_id: str,
    store: UsageStore = Depends(get_usage_store),
) -> dict[str, Any]:
    """Return usage rollup for a tracked session."""
    detail = await store.get_session(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _serialize_session(detail)
