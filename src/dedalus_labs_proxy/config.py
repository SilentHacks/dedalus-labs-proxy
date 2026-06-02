"""Configuration management for Dedalus Labs Proxy."""

import json
import os
import sys

from dotenv import load_dotenv

from dedalus_labs_proxy.usage.context_limits import build_context_limits

load_dotenv()


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""


class Config:
    """Application configuration loaded from environment variables."""

    def __init__(self, require_api_key: bool = True) -> None:
        """Initialize configuration from environment variables.

        Args:
            require_api_key: If True, raise ConfigurationError if DEDALUS_API_KEY
                is not set.
        """
        self.dedalus_api_key = os.getenv("DEDALUS_API_KEY")
        if require_api_key and not self.dedalus_api_key:
            raise ConfigurationError(
                "DEDALUS_API_KEY environment variable is required"
            )

        self.host = os.getenv("HOST", "localhost")
        self.port = int(os.getenv("PORT", "8000"))
        self.dedalus_base_url = os.getenv(
            "DEDALUS_BASE_URL", "https://api.dedaluslabs.ai"
        )
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.max_tokens = int(os.getenv("MAX_TOKENS", "4096"))
        self.temperature = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))
        self.timeout = float(os.getenv("REQUEST_TIMEOUT", "300"))
        self.max_retries = int(os.getenv("MAX_RETRIES", "2"))
        self.stream_keepalive_interval = float(
            os.getenv("STREAM_KEEPALIVE_INTERVAL", "15")
        )
        self.tool_max_tokens = int(os.getenv("TOOL_MAX_TOKENS", "128000"))
        cors_origins = os.getenv("CORS_ORIGINS", "*")
        self.cors_origins = (
            ["*"]
            if cors_origins.strip() == "*"
            else [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
        )
        self.disable_docs = os.getenv("DISABLE_DOCS", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        self.proxy_api_keys = frozenset(
            k.strip()
            for k in os.getenv("PROXY_API_KEYS", "").split(",")
            if k.strip()
        )
        self.usage_tracking = os.getenv("USAGE_TRACKING", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        self.usage_log = os.getenv("USAGE_LOG", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        self.usage_headers = os.getenv("USAGE_HEADERS", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        self.usage_sse_metadata = os.getenv("USAGE_SSE_METADATA", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        self.usage_admin_enabled = os.getenv("USAGE_ADMIN_ENABLED", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        self.usage_admin_keys = frozenset(
            k.strip()
            for k in os.getenv("USAGE_ADMIN_KEYS", "").split(",")
            if k.strip()
        )
        self.usage_store_max_records = int(os.getenv("USAGE_STORE_MAX_RECORDS", "1000"))
        self.usage_session_ttl_seconds = float(
            os.getenv("USAGE_SESSION_TTL_SECONDS", "86400")
        )
        self.usage_chars_per_token = int(os.getenv("USAGE_CHARS_PER_TOKEN", "4"))
        if self.usage_tracking:
            self.usage_context_limits = self._load_usage_context_limits()
        else:
            self.usage_context_limits = build_context_limits()
        if self.usage_admin_enabled and not self.usage_admin_keys:
            raise ConfigurationError(
                "USAGE_ADMIN_ENABLED requires USAGE_ADMIN_KEYS to be set"
            )

    def _load_usage_context_limits(self) -> dict[str, int]:
        raw = os.getenv("USAGE_CONTEXT_LIMITS_JSON")
        if not raw:
            return build_context_limits()
        try:
            overrides = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                "USAGE_CONTEXT_LIMITS_JSON must be valid JSON"
            ) from exc
        if not isinstance(overrides, dict):
            raise ConfigurationError(
                "USAGE_CONTEXT_LIMITS_JSON must be a JSON object"
            )
        parsed: dict[str, int] = {}
        for key, value in overrides.items():
            if not isinstance(key, str) or not isinstance(value, int):
                raise ConfigurationError(
                    "USAGE_CONTEXT_LIMITS_JSON must map model names to integers"
                )
            parsed[key] = value
        return build_context_limits(parsed)


# Global config instance - initialized lazily to allow testing
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def init_config(require_api_key: bool = True) -> Config:
    """Initialize and return the global configuration.

    Args:
        require_api_key: If True, raise ConfigurationError if DEDALUS_API_KEY
            is not set.

    Returns:
        The configuration instance.

    Raises:
        ConfigurationError: If required configuration is missing.
    """
    global _config
    try:
        _config = Config(require_api_key=require_api_key)
    except ConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    return _config
