"""Chat completions endpoint."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from dedalus_labs_proxy.dependencies import (
    get_dedalus_client,
    get_usage_tracker,
    maybe_begin_usage,
)
from dedalus_labs_proxy.models.requests import ChatCompletionRequest
from dedalus_labs_proxy.models.responses import ChatCompletionResponse
from dedalus_labs_proxy.services.completion.service import ChatCompletionService
from dedalus_labs_proxy.services.completion.sse import SSE_HEADERS
from dedalus_labs_proxy.services.dedalus import DedalusClient
from dedalus_labs_proxy.usage.tracker import UsageTracker

router = APIRouter()


def _get_completion_service(
    client: DedalusClient = Depends(get_dedalus_client),
) -> ChatCompletionService:
    return ChatCompletionService(client)


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
    service: ChatCompletionService = Depends(_get_completion_service),
    tracker: UsageTracker | None = Depends(get_usage_tracker),
) -> ChatCompletionResponse | StreamingResponse | JSONResponse:
    """Handle chat completion requests."""
    usage_ctx = maybe_begin_usage(request, body)
    service.log_request(body)

    if body.stream:
        return StreamingResponse(
            service.stream(body, usage_ctx=usage_ctx, tracker=tracker),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    result = await service.complete(body, usage_ctx=usage_ctx, tracker=tracker)
    if tracker is None or usage_ctx is None:
        return result

    headers = tracker.build_response_headers(usage_ctx)
    if not headers:
        return result

    return JSONResponse(content=result.model_dump(exclude_none=True), headers=headers)
