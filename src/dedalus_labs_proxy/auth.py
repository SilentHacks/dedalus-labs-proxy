"""Optional client authentication for the proxy."""

import secrets

from fastapi import Request, status
from fastapi.responses import JSONResponse

MISSING_API_KEY_MESSAGE = (
    "You didn't provide an API key. Provide one via Authorization: Bearer <key>."
)
INVALID_API_KEY_MESSAGE = "Incorrect API key provided."


def extract_bearer_token(authorization: str | None) -> str | None:
    """Parse a Bearer token from an Authorization header."""
    if not authorization:
        return None

    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials:
        return None

    return credentials


def is_exempt_from_proxy_auth(method: str, path: str) -> bool:
    """Return True when proxy auth should not be enforced."""
    if method == "OPTIONS":
        return True
    if path == "/health":
        return True
    return path.startswith("/v1/admin/")


def proxy_auth_error_response(detail: str) -> JSONResponse:
    """Return an OpenAI-compatible 401 authentication error."""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "error": {
                "message": detail,
                "type": "authentication_error",
            }
        },
    )


def _is_valid_api_key(token: str, allowed_keys: frozenset[str]) -> bool:
    """Check token against allowed keys using constant-time comparison."""
    return any(secrets.compare_digest(token, key) for key in allowed_keys)


def validate_proxy_auth(
    request: Request, allowed_keys: frozenset[str]
) -> JSONResponse | None:
    """Validate client bearer auth; return error response or None if allowed."""
    if is_exempt_from_proxy_auth(request.method, request.url.path):
        return None

    token = extract_bearer_token(request.headers.get("authorization"))
    if token is None:
        return proxy_auth_error_response(MISSING_API_KEY_MESSAGE)
    if not _is_valid_api_key(token, allowed_keys):
        return proxy_auth_error_response(INVALID_API_KEY_MESSAGE)
    return None


def validate_admin_auth(
    request: Request, admin_keys: frozenset[str]
) -> JSONResponse | None:
    """Validate admin bearer auth; return error response or None if allowed."""
    token = extract_bearer_token(request.headers.get("authorization"))
    if token is None:
        return proxy_auth_error_response(MISSING_API_KEY_MESSAGE)
    if not _is_valid_api_key(token, admin_keys):
        return proxy_auth_error_response(INVALID_API_KEY_MESSAGE)
    return None
