"""SSE keepalive wrapper for long-running streams."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any


async def iter_with_keepalive(
    stream: Any,
    keepalive_interval: float,
) -> AsyncGenerator[Any, None]:
    """Yield stream items, signaling None when a keepalive ping is needed."""
    stream_iter = stream.__aiter__()
    pending_next: asyncio.Task[Any] | None = None

    while True:
        try:
            if pending_next is None:
                pending_next = asyncio.create_task(stream_iter.__anext__())

            try:
                chunk = await asyncio.wait_for(
                    asyncio.shield(pending_next),
                    timeout=keepalive_interval,
                )
                pending_next = None
                yield chunk
            except TimeoutError:
                yield None
        except StopAsyncIteration:
            break
