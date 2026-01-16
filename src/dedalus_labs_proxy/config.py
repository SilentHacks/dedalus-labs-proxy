"""Configuration management for Dedalus Labs Proxy."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

MODEL_MAP: dict[str, str] = {
    "gpt-4": "openai/gpt-4",
    "gpt-4-turbo": "openai/gpt-4-turbo",
    "gpt-4o": "openai/gpt-4o",
    "gpt-4o-mini": "openai/gpt-4o-mini",
    "gpt-3.5-turbo": "openai/gpt-3.5-turbo",
    "claude-3-opus": "anthropic/claude-3-opus",
    "claude-3-sonnet": "anthropic/claude-3-sonnet",
    "claude-3-haiku": "anthropic/claude-3-haiku",
    "gemini-pro": "google/gemini-pro",
    "gemini-1.5-pro": "google/gemini-1.5-pro",
    "gemini-1.5-flash": "google/gemini-1.5-flash",
}


class Config:
    """Application configuration loaded from environment variables."""

    def __init__(self, require_api_key: bool = True) -> None:
        """Initialize configuration from environment variables.

        Args:
            require_api_key: If True, exit if DEDALUS_API_KEY is not set.
        """
        self.dedalus_api_key = os.getenv("DEDALUS_API_KEY")
        if require_api_key and not self.dedalus_api_key:
            print("Error: DEDALUS_API_KEY environment variable is required", file=sys.stderr)
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
        self.MODEL_MAP = MODEL_MAP

    def get_model_name(self, model: str) -> str:
        """Map a model alias to its Dedalus API model name.

        Args:
            model: Model name or alias.

        Returns:
            The Dedalus API model name.
        """
        return MODEL_MAP.get(model, model)

    def is_valid_model(self, model: str) -> bool:
        """Check if a model name is valid.

        Args:
            model: Model name to validate.

        Returns:
            True if the model is valid.
        """
        if model in MODEL_MAP:
            return True
        if "/" in model:
            return True
        return False


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
