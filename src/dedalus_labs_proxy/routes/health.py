"""Health check endpoints."""

from typing import Any

import dedalus_labs
from fastapi import APIRouter, HTTPException

from dedalus_labs_proxy.logging import logger
from dedalus_labs_proxy.services.dedalus import global_client

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Fast local health check.

    Returns:
        Status object with "ok" status.
    """
    return {"status": "ok"}


@router.get("/health/dedalus")
async def dedalus_health_check() -> dict[str, Any]:
    """Check the Dedalus API connection.

    Returns:
        Status object with connection verification result.

    Raises:
        HTTPException: If authentication or connection fails.
    """
    logger.info("Dedalus API health check initiated")

    try:
        await global_client.verify_connection()
        logger.info("Dedalus API health check passed")
        return {
            "status": "ok",
            "service": "dedalus-api",
            "message": "API connection verified",
        }
    except dedalus_labs.AuthenticationError:
        logger.error("Dedalus API authentication failed during health check")
        raise HTTPException(
            status_code=401, detail="Dedalus API authentication failed"
        ) from None
    except dedalus_labs.APIConnectionError:
        logger.error("Dedalus API connection failed during health check")
        raise HTTPException(
            status_code=503, detail="Cannot connect to Dedalus API"
        ) from None
