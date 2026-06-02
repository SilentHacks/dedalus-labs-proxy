"""FastAPI application for Dedalus Labs Proxy."""

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from dedalus_labs_proxy.auth import validate_proxy_auth
from dedalus_labs_proxy.config import ConfigurationError, get_config, init_config
from dedalus_labs_proxy.logging import logger, sanitize_log_data
from dedalus_labs_proxy.routes import (
    admin_usage_router,
    chat_router,
    health_router,
    models_router,
)
from dedalus_labs_proxy.services.dedalus import create_dedalus_client
from dedalus_labs_proxy.usage.bootstrap import ensure_usage_tracking


def _parse_cors_origins() -> list[str]:
    cors_origins = os.getenv("CORS_ORIGINS", "*")
    if cors_origins.strip() == "*":
        return ["*"]
    return [origin.strip() for origin in cors_origins.split(",") if origin.strip()]


def _docs_disabled() -> bool:
    return os.getenv("DISABLE_DOCS", "false").lower() in ("1", "true", "yes")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config = init_config(require_api_key=True)
    app.state.dedalus_client = create_dedalus_client()
    ensure_usage_tracking(app, config)
    yield
    await app.state.dedalus_client.close()


app = FastAPI(
    title="Dedalus Labs Proxy",
    description="OpenAI-compatible proxy for Dedalus Labs API",
    version="0.3.0",
    lifespan=lifespan,
    docs_url=None if _docs_disabled() else "/docs",
    redoc_url=None if _docs_disabled() else "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def proxy_auth_middleware(request: Request, call_next: Any) -> Any:
    """Enforce optional client bearer auth when PROXY_API_KEYS is configured."""
    config = get_config()
    if config.proxy_api_keys:
        if error := validate_proxy_auth(request, config.proxy_api_keys):
            return error
    return await call_next(request)


@app.middleware("http")
async def log_requests_responses(request: Request, call_next: Any) -> Any:
    """Log incoming requests and outgoing responses."""
    start_time = time.time()

    logger.info(
        "Request: %s %s | Headers: %s",
        request.method,
        request.url.path,
        sanitize_log_data(dict(request.headers)),
    )

    try:
        response = await call_next(request)
    except Exception as e:
        logger.error("Request failed: %s | Error: %s", request.url.path, str(e))
        raise

    process_time = (time.time() - start_time) * 1000
    logger.info(
        "Response: %s %s | Status: %d | Time: %.2fms",
        request.method,
        request.url.path,
        response.status_code,
        process_time,
    )

    return response


@app.exception_handler(ConfigurationError)
async def configuration_error_handler(
    request: Request, exc: ConfigurationError
) -> JSONResponse:
    """Handle missing configuration with a structured 503 response."""
    logger.error(
        "Configuration error on %s %s: %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": {
                "message": "Server not configured",
                "type": "configuration_error",
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle validation errors with OpenAI-compatible error format."""
    logger.warning(
        "Validation error on %s %s: %s",
        request.method,
        request.url.path,
        str(exc.errors()),
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "message": "Invalid request data",
                "type": "validation_error",
                "details": exc.errors(),
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions with OpenAI-compatible error format."""
    error_type = "http_error"
    if exc.status_code == 401:
        error_type = "authentication_error"

    logger.warning(
        "HTTP error on %s %s: %d - %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": str(exc.detail),
                "type": error_type,
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "message": "Internal server error",
                "type": "internal_error",
            }
        },
    )


app.include_router(health_router)
app.include_router(models_router)
app.include_router(chat_router)
app.include_router(admin_usage_router)
