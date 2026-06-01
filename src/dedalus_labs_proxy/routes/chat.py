"""Chat completions endpoint."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from dedalus_labs_proxy.dependencies import get_dedalus_client
from dedalus_labs_proxy.models.requests import ChatCompletionRequest
from dedalus_labs_proxy.models.responses import ChatCompletionResponse
from dedalus_labs_proxy.services.completion.service import ChatCompletionService
from dedalus_labs_proxy.services.completion.sse import SSE_HEADERS
from dedalus_labs_proxy.services.dedalus import DedalusClient

router = APIRouter()


def _get_completion_service(
    client: DedalusClient = Depends(get_dedalus_client),
) -> ChatCompletionService:
    return ChatCompletionService(client)


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
    service: ChatCompletionService = Depends(_get_completion_service),
) -> ChatCompletionResponse | StreamingResponse:
    """Handle chat completion requests."""
    service.log_request(request)

    if request.stream:
        return StreamingResponse(
            service.stream(request),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    return await service.complete(request)
