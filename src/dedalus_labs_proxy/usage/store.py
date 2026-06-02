"""In-memory usage record store."""

import asyncio
from collections import deque

from dedalus_labs_proxy.usage.models import (
    ClientUsageStats,
    ModelUsageStats,
    SessionDetail,
    SessionStats,
    UsageRecord,
    UsageSummary,
)


class UsageStore:
    """Thread-safe in-memory ring buffer for usage records."""

    def __init__(
        self,
        *,
        max_records: int = 1000,
        session_ttl_seconds: float = 86400,
    ) -> None:
        self._max_records = max_records
        self._session_ttl_seconds = session_ttl_seconds
        self._records: deque[UsageRecord] = deque(maxlen=max_records)
        self._sessions: dict[str, SessionStats] = {}
        self._lock = asyncio.Lock()

    async def record(self, record: UsageRecord) -> SessionStats | None:
        """Store a usage record and update session aggregates."""
        async with self._lock:
            self._records.append(record)
            self._cleanup_expired_sessions(record.timestamp)
            if record.session_id is None:
                return None
            session = self._sessions.get(record.session_id)
            if session is None:
                session = SessionStats(session_id=record.session_id)
                self._sessions[record.session_id] = session
            session.request_count += 1
            session.last_seen = record.timestamp
            if record.total_tokens is not None:
                session.total_tokens += record.total_tokens
            if record.prompt_tokens is not None:
                session.total_prompt_tokens += record.prompt_tokens
            if record.completion_tokens is not None:
                session.total_completion_tokens += record.completion_tokens
            return session

    async def get_summary(self) -> UsageSummary:
        """Return aggregate usage across stored records."""
        async with self._lock:
            by_model: dict[str, ModelUsageStats] = {}
            by_client: dict[str, ClientUsageStats] = {}
            total_tokens = 0

            for record in self._records:
                total_tokens += record.total_tokens or 0
                model_stats = by_model.setdefault(record.model, ModelUsageStats())
                model_stats.requests += 1
                model_stats.total_tokens += record.total_tokens or 0

                if record.client_key_hash is not None:
                    client_stats = by_client.setdefault(
                        record.client_key_hash, ClientUsageStats()
                    )
                    client_stats.requests += 1
                    client_stats.total_tokens += record.total_tokens or 0

            return UsageSummary(
                period="all_time_in_memory",
                total_requests=len(self._records),
                total_tokens=total_tokens,
                by_model=by_model,
                by_client=by_client,
            )

    async def get_session(self, session_id: str) -> SessionDetail | None:
        """Return session stats and recent matching records."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            recent = [
                record
                for record in reversed(self._records)
                if record.session_id == session_id
            ]
            return SessionDetail(session=session, recent_requests=recent)

    async def recent_records(self, limit: int = 100) -> list[UsageRecord]:
        """Return the most recent usage records."""
        async with self._lock:
            if limit <= 0:
                return []
            return list(reversed(list(self._records)[-limit:]))

    def _cleanup_expired_sessions(self, now: float) -> None:
        expired = [
            session_id
            for session_id, stats in self._sessions.items()
            if now - stats.last_seen > self._session_ttl_seconds
        ]
        for session_id in expired:
            del self._sessions[session_id]
