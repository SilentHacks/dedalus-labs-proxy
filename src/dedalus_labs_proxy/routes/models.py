"""Models listing endpoint."""

from typing import Any

from fastapi import APIRouter

from dedalus_labs_proxy.config import get_config
from dedalus_labs_proxy.logging import logger

router = APIRouter()


@router.get("/v1/models")
async def list_models() -> dict[str, Any]:
    """List available models.

    Returns:
        OpenAI-compatible model list response.
    """
    logger.info("Listing available models")
    config = get_config()
    models = []
    for provider_id, _dedalus_id in config.MODEL_MAP.items():
        models.append(
            {
                "id": provider_id,
                "object": "model",
                "created": 1704067200,
                "owned_by": "dedalus",
            }
        )
    return {"object": "list", "data": models}
