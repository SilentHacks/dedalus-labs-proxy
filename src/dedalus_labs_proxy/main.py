"""FastAPI application for Dedalus Labs Proxy."""

import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from dedalus_labs_proxy.logging import logger, sanitize_log_data
from dedalus_labs_proxy.routes import chat_router, health_router, models_router

app = FastAPI(
    title="Dedalus Labs Proxy",
    description="OpenAI-compatible proxy for Dedalus Labs API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
