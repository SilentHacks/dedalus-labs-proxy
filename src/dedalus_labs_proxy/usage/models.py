"""Data models for usage tracking."""

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TokenUsage:
    """Token counts from an upstream completion."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class UsageRecord:
    """Immutable snapshot of one completion request."""

    request_id: str
    timestamp: float
    model: str
    stream: bool
    message_count: int
    tool_count: int
    context_estimate_tokens: int
    context_window_tokens: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    finish_reason: str | None
    latency_ms: float
    client_key_hash: str | None
    session_id: str | None
    error: bool


@dataclass
class SessionStats:
    """Aggregated usage for a client session."""

    session_id: str
    request_count: int = 0
    total_tokens: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    last_seen: float = 0.0


@dataclass
class ModelUsageStats:
    """Per-model aggregate counters."""

    requests: int = 0
    total_tokens: int = 0


@dataclass
class ClientUsageStats:
    """Per-client-key aggregate counters."""

    requests: int = 0
    total_tokens: int = 0


@dataclass
class UsageSummary:
    """Roll-up for the admin usage endpoint."""

    period: str
    total_requests: int
    total_tokens: int
    by_model: dict[str, ModelUsageStats] = field(default_factory=dict)
    by_client: dict[str, ClientUsageStats] = field(default_factory=dict)


@dataclass
class SessionDetail:
    """Session rollup with recent request records."""

    session: SessionStats
    recent_requests: list[UsageRecord] = field(default_factory=list)


@dataclass
class UsageContext:
    """Mutable per-request tracking state."""

    request_id: str
    started_at: float
    model: str
    stream: bool
    message_count: int
    tool_count: int
    context_estimate_tokens: int
    context_window_tokens: int | None
    client_key_hash: str | None
    session_id: str | None
    client_requested_usage_in_stream: bool = False
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None
    session_total_tokens: int | None = None
    error: bool = False

    def set_usage(self, usage: TokenUsage | None) -> None:
        if usage is None:
            return
        self.prompt_tokens = usage.prompt_tokens
        self.completion_tokens = usage.completion_tokens
        self.total_tokens = usage.total_tokens

    def context_utilization(self) -> float | None:
        if self.context_window_tokens is None or self.context_window_tokens <= 0:
            return None
        return min(
            1.0,
            self.context_estimate_tokens / self.context_window_tokens,
        )

    def latency_ms(self) -> float:
        return (time.time() - self.started_at) * 1000

    def to_log_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "event": "completion_usage",
            "request_id": self.request_id,
            "model": self.model,
            "stream": self.stream,
            "message_count": self.message_count,
            "tool_count": self.tool_count,
            "context_estimate_tokens": self.context_estimate_tokens,
            "latency_ms": round(self.latency_ms(), 2),
            "error": self.error,
        }
        if self.prompt_tokens is not None:
            data["prompt_tokens"] = self.prompt_tokens
        if self.completion_tokens is not None:
            data["completion_tokens"] = self.completion_tokens
        if self.total_tokens is not None:
            data["total_tokens"] = self.total_tokens
        utilization = self.context_utilization()
        if utilization is not None:
            data["context_utilization_pct"] = round(utilization * 100, 2)
        if self.session_id is not None:
            data["session_id"] = self.session_id
        if self.session_total_tokens is not None:
            data["session_total_tokens"] = self.session_total_tokens
        if self.finish_reason is not None:
            data["finish_reason"] = self.finish_reason
        return data
