"""Logging configuration for Dedalus Labs Proxy."""

import json
import logging
import sys
from typing import Any


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as JSON."""
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


def setup_logging(
    level: str = "INFO",
    json_output: bool = False,
) -> logging.Logger:
    """Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        json_output: If True, output logs as JSON.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("dedalus-proxy")
    logger.setLevel(getattr(logging, level.upper()))

    # Clear any existing handlers
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))

    formatter: logging.Formatter
    if json_output:
        formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger


def sanitize_log_data(data: Any, sensitive_fields: list[str] | None = None) -> Any:
    """Remove sensitive data from logs.

    Args:
        data: Data to sanitize (dict, list, or primitive).
        sensitive_fields: List of field names to redact.

    Returns:
        Sanitized data with sensitive values replaced by '[REDACTED]'.
    """
    if sensitive_fields is None:
        sensitive_fields = ["api_key", "password", "token", "authorization", "bearer"]

    if isinstance(data, dict):
        return {
            k: (
                "[REDACTED]"
                if any(s in k.lower() for s in sensitive_fields)
                else sanitize_log_data(v, sensitive_fields)
            )
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [sanitize_log_data(item, sensitive_fields) for item in data]
    else:
        return data


# Default logger - will be reconfigured when CLI runs
logger = logging.getLogger("dedalus-proxy")
