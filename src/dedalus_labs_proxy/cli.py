"""CLI entry point for Dedalus Labs Proxy."""

import argparse

import uvicorn

from dedalus_labs_proxy.config import get_config, init_config
from dedalus_labs_proxy.logging import setup_logging


def main() -> None:
    """Main entry point for the dedalus-proxy CLI."""
    # Load config from env first so argparse defaults reflect HOST/PORT/LOG_LEVEL
    init_config(require_api_key=True)
    config = get_config()

    parser = argparse.ArgumentParser(
        prog="dedalus-proxy",
        description="OpenAI-compatible proxy for Dedalus Labs API",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.port,
        help=f"Port to run the server on (default: {config.port}, env PORT)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=config.host,
        help=f"Host to bind the server to (default: {config.host}, env HOST)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["debug", "info", "warning", "error"],
        default=config.log_level.lower(),
        help=f"Log level (default: {config.log_level.lower()}, env LOG_LEVEL)",
    )
    parser.add_argument(
        "--json-logs",
        action="store_true",
        help="Output logs in JSON format",
    )

    args = parser.parse_args()

    setup_logging(level=args.log_level, json_output=args.json_logs)

    print(f"Dedalus proxy running on http://{args.host}:{args.port}")

    uvicorn.run(
        "dedalus_labs_proxy.main:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
