"""Models listing endpoint."""

from typing import Any

import dedalus_labs
from fastapi import APIRouter, Depends, HTTPException

from dedalus_labs_proxy.dependencies import get_dedalus_client
from dedalus_labs_proxy.logging import logger
from dedalus_labs_proxy.services.dedalus import DedalusClient

router = APIRouter()


@router.get("/v1/models")
async def list_models(
    client: DedalusClient = Depends(get_dedalus_client),
) -> dict[str, Any]:
    """List available models from the Dedalus Labs API."""
    logger.info("Listing available models from Dedalus API")

    try:
        response = await client.list_models()
        if hasattr(response, "model_dump"):
            return response.model_dump()
        if isinstance(response, dict):
            return response
        return {"object": "list", "data": list(response)}
    except dedalus_labs.AuthenticationError:
        raise HTTPException(
            status_code=401, detail="Dedalus API authentication failed"
        ) from None
    except dedalus_labs.APIConnectionError:
        raise HTTPException(
            status_code=503, detail="Cannot connect to Dedalus API"
        ) from None
