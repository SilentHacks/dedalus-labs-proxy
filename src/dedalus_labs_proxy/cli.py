"""CLI entry point for Dedalus Labs Proxy."""

import argparse

import uvicorn

from dedalus_labs_proxy.config import init_config
from dedalus_labs_proxy.logging import setup_logging


def main() -> None:
    """Main entry point for the dedalus-proxy CLI."""
    parser = argparse.ArgumentParser(
        prog="dedalus-proxy",
        description="OpenAI-compatible proxy for Dedalus Labs API",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the server on (default: 8000)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Host to bind the server to (default: localhost)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="Log level (default: info)",
    )
    parser.add_argument(
        "--json-logs",
        action="store_true",
        help="Output logs in JSON format",
    )

    args = parser.parse_args()

    # Initialize configuration (will exit if DEDALUS_API_KEY is missing)
    init_config(require_api_key=True)

    # Setup logging
    setup_logging(level=args.log_level, json_output=args.json_logs)

    # Log startup message
    print(f"Dedalus proxy running on http://{args.host}:{args.port}")

    # Run the server
    uvicorn.run(
        "dedalus_labs_proxy.main:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
