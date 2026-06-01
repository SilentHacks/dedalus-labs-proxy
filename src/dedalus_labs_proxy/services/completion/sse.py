"""Server-Sent Events formatting helpers."""

from collections.abc import AsyncGenerator

import orjson

from dedalus_labs_proxy.models.responses import ChatCompletionChunk

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

SSE_DONE = "data: [DONE]\n\n"
SSE_PING = ": ping\n\n"


def format_chunk(chunk: ChatCompletionChunk) -> str:
    """Format a chat completion chunk as an SSE data event."""
    return f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"


def format_error_payload(error_data: dict[str, object]) -> str:
    """Format an error dict as an SSE data event."""
    return f"data: {orjson.dumps(error_data).decode()}\n\n"


async def yield_sse_error(error_data: dict[str, object]) -> AsyncGenerator[str, None]:
    """Yield an SSE error event followed by the stream terminator."""
    yield format_error_payload(error_data)
    yield SSE_DONE
