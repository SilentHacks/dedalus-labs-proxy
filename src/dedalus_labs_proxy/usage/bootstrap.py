"""Bootstrap helpers for usage tracking."""

from fastapi import FastAPI

from dedalus_labs_proxy.config import Config, get_config
from dedalus_labs_proxy.usage.store import UsageStore
from dedalus_labs_proxy.usage.tracker import UsageTracker


def ensure_usage_tracking(app: FastAPI, config: Config | None = None) -> None:
    """Initialize usage tracking state on the app when enabled."""
    config = config or get_config()
    if not config.usage_tracking:
        app.state.usage_store = None
        app.state.usage_tracker = None
        return

    if getattr(app.state, "usage_tracker", None) is not None:
        return

    app.state.usage_store = UsageStore(
        max_records=config.usage_store_max_records,
        session_ttl_seconds=config.usage_session_ttl_seconds,
    )
    app.state.usage_tracker = UsageTracker(app.state.usage_store, config)
