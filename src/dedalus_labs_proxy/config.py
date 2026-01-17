"""Configuration management for Dedalus Labs Proxy."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    def __init__(self, require_api_key: bool = True) -> None:
        """Initialize configuration from environment variables.

        Args:
            require_api_key: If True, exit if DEDALUS_API_KEY is not set.
        """
        self.dedalus_api_key = os.getenv("DEDALUS_API_KEY")
        if require_api_key and not self.dedalus_api_key:
            print(
                "Error: DEDALUS_API_KEY environment variable is required",
                file=sys.stderr,
            )
            sys.exit(1)

        self.host = os.getenv("HOST", "0.0.0.0")
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
        # Default max tokens for tool-enabled requests (large to support file writes)
        self.tool_max_tokens = int(os.getenv("TOOL_MAX_TOKENS", "128000"))


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
        require_api_key: If True, exit if DEDALUS_API_KEY is not set.

    Returns:
        The configuration instance.
    """
    global _config
    _config = Config(require_api_key=require_api_key)
    return _config
