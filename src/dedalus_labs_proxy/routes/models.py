"""Models listing endpoint."""

from typing import Any

from fastapi import APIRouter

from dedalus_labs_proxy.logging import logger

router = APIRouter()


@router.get("/v1/models")
async def list_models() -> dict[str, Any]:
    """List available models.

    Returns an empty list. Users should pass model names directly as expected
    by the Dedalus Labs API (e.g., 'openai/gpt-4o', 'anthropic/claude-3-sonnet').

    Returns:
        OpenAI-compatible model list response (empty).
    """
    logger.info(
        "Listing available models (no predefined list - use Dedalus model names directly)"
    )
    return {"object": "list", "data": []}
