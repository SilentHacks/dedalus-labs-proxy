"""Usage tracking orchestration."""

import hashlib
import json
import logging
import re
import time
import uuid
from typing import Any

from fastapi import Request

from dedalus_labs_proxy.auth import extract_bearer_token
from dedalus_labs_proxy.config import Config
from dedalus_labs_proxy.models.requests import ChatCompletionRequest
from dedalus_labs_proxy.usage.context_limits import get_context_window
from dedalus_labs_proxy.usage.estimator import estimate_context_tokens
from dedalus_labs_proxy.usage.models import TokenUsage, UsageContext, UsageRecord
from dedalus_labs_proxy.usage.store import UsageStore

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_usage_logger = logging.getLogger("dedalus-proxy")


def hash_client_key(token: str) -> str:
    """Return a short hash of a client API key."""
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def parse_session_id(header_value: str | None) -> str | None:
    """Validate and return a session id from the request header."""
    if header_value is None:
        return None
    value = header_value.strip()
    if not value or not SESSION_ID_PATTERN.fullmatch(value):
        return None
    return value


def client_requested_stream_usage(request: ChatCompletionRequest) -> bool:
    """Return True when the client asked for usage in the stream."""
    extra = request.model_extra or {}
    stream_options = extra.get("stream_options")
    if not isinstance(stream_options, dict):
        return False
    return bool(stream_options.get("include_usage"))


class UsageTracker:
    """Coordinates per-request usage capture and output."""

    def __init__(self, store: UsageStore, config: Config) -> None:
        self._store = store
        self._config = config

    def begin(
        self,
        *,
        request: Request,
        chat_request: ChatCompletionRequest,
        messages: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> UsageContext:
        """Create a usage context for a completion request."""
        token = extract_bearer_token(request.headers.get("authorization"))
        client_key_hash = hash_client_key(token) if token else None
        session_id = parse_session_id(request.headers.get("x-proxy-session-id"))

        estimate_messages = messages
        estimate_tools = tools
        if estimate_messages is None:
            estimate_messages = [
                msg.model_dump(exclude_none=True) for msg in chat_request.messages
            ]
        if estimate_tools is None and chat_request.tools:
            estimate_tools = [
                tool.model_dump(exclude_none=True) for tool in chat_request.tools
            ]

        context_estimate = estimate_context_tokens(
            estimate_messages,
            estimate_tools,
            chars_per_token=self._config.usage_chars_per_token,
        )
        context_window = get_context_window(
            chat_request.model, self._config.usage_context_limits
        )

        ctx = UsageContext(
            request_id=str(uuid.uuid4()),
            started_at=time.time(),
            model=chat_request.model,
            stream=chat_request.stream,
            message_count=len(chat_request.messages),
            tool_count=len(chat_request.tools) if chat_request.tools else 0,
            context_estimate_tokens=context_estimate,
            context_window_tokens=context_window,
            client_key_hash=client_key_hash,
            session_id=session_id,
            client_requested_usage_in_stream=client_requested_stream_usage(
                chat_request
            ),
        )
        request.state.usage_context = ctx
        return ctx

    async def finalize(
        self,
        ctx: UsageContext,
        *,
        usage: TokenUsage | None = None,
        finish_reason: str | None = None,
        error: bool = False,
    ) -> None:
        """Persist usage metrics and emit optional logs."""
        ctx.set_usage(usage)
        ctx.finish_reason = finish_reason
        ctx.error = error

        record = UsageRecord(
            request_id=ctx.request_id,
            timestamp=time.time(),
            model=ctx.model,
            stream=ctx.stream,
            message_count=ctx.message_count,
            tool_count=ctx.tool_count,
            context_estimate_tokens=ctx.context_estimate_tokens,
            context_window_tokens=ctx.context_window_tokens,
            prompt_tokens=ctx.prompt_tokens,
            completion_tokens=ctx.completion_tokens,
            total_tokens=ctx.total_tokens,
            finish_reason=ctx.finish_reason,
            latency_ms=ctx.latency_ms(),
            client_key_hash=ctx.client_key_hash,
            session_id=ctx.session_id,
            error=ctx.error,
        )
        session = await self._store.record(record)
        if session is not None:
            ctx.session_total_tokens = session.total_tokens

        if self._config.usage_log:
            _usage_logger.info(json.dumps(ctx.to_log_dict()))

    def build_response_headers(self, ctx: UsageContext) -> dict[str, str]:
        """Build optional usage response headers."""
        if not self._config.usage_headers:
            return {}

        headers = {"X-Proxy-Request-Id": ctx.request_id}
        if ctx.prompt_tokens is not None:
            headers["X-Proxy-Prompt-Tokens"] = str(ctx.prompt_tokens)
        if ctx.completion_tokens is not None:
            headers["X-Proxy-Completion-Tokens"] = str(ctx.completion_tokens)
        if ctx.total_tokens is not None:
            headers["X-Proxy-Total-Tokens"] = str(ctx.total_tokens)
        headers["X-Proxy-Context-Estimate"] = str(ctx.context_estimate_tokens)
        utilization = ctx.context_utilization()
        if utilization is not None:
            headers["X-Proxy-Context-Utilization"] = f"{utilization:.4f}"
        if ctx.session_id is not None:
            headers["X-Proxy-Session-Id"] = ctx.session_id
        if ctx.session_total_tokens is not None:
            headers["X-Proxy-Session-Total-Tokens"] = str(ctx.session_total_tokens)
        return headers

    def build_sse_metadata_comment(self, ctx: UsageContext) -> str | None:
        """Build an SSE comment line with usage metadata."""
        if not self._config.usage_sse_metadata:
            return None

        payload: dict[str, Any] = {"request_id": ctx.request_id}
        if ctx.prompt_tokens is not None:
            payload["prompt_tokens"] = ctx.prompt_tokens
        if ctx.completion_tokens is not None:
            payload["completion_tokens"] = ctx.completion_tokens
        if ctx.total_tokens is not None:
            payload["total_tokens"] = ctx.total_tokens
        if ctx.session_total_tokens is not None:
            payload["session_total_tokens"] = ctx.session_total_tokens
        utilization = ctx.context_utilization()
        if utilization is not None:
            payload["context_utilization"] = round(utilization, 4)

        return f": x-proxy-usage {json.dumps(payload, separators=(',', ':'))}\n\n"
