"""Command line entry point.

    python -m mcp_server serve                     # MCP over stdio (default)
    python -m mcp_server serve --transport streamable-http --host 127.0.0.1 --port 8765
    python -m mcp_server sync-once                 # one Allegro sync, no LLM
    python -m mcp_server sync-loop --interval 300  # sync every five minutes
"""
import argparse
import asyncio
import logging
import os
import sys

from . import __version__
from .client import PackingClient, PackingError
from .config import Settings
from .server import create_server
from .sync_loop import run_loop, sync_once

logger = logging.getLogger("packing_mcp")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mcp_server",
        description="MCP server for the Packing (Weles) app, plus a headless Allegro sync.",
    )
    parser.add_argument("--version", action="version", version=f"packing-mcp {__version__}")
    parser.add_argument(
        "--log-level",
        default=os.getenv("PACKING_LOG_LEVEL", "INFO").upper(),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="log verbosity (default: INFO); logs go to stderr so stdio stays clean",
    )
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="run the MCP server (default)")
    serve.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=os.getenv("PACKING_MCP_TRANSPORT", "stdio"),
        help="MCP transport (default: stdio)",
    )
    serve.add_argument("--host", default=None, help="bind address for streamable-http")
    serve.add_argument("--port", type=int, default=None, help="port for streamable-http")
    parser.set_defaults(host=None, port=None, transport=os.getenv("PACKING_MCP_TRANSPORT", "stdio"))

    once = subparsers.add_parser("sync-once", help="run one Allegro order sync and exit")
    once.set_defaults(command="sync-once")

    loop = subparsers.add_parser("sync-loop", help="sync Allegro orders on a fixed interval")
    loop.add_argument(
        "--interval",
        type=float,
        default=float(os.getenv("PACKING_SYNC_INTERVAL", "300")),
        help="seconds between syncs (default: 300)",
    )
    loop.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="stop after N syncs (default: run until SIGINT/SIGTERM)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        settings = Settings.from_env()
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        return 2

    command = args.command or "serve"
    if command == "serve":
        server = create_server(settings, host=args.host, port=args.port)
        logger.info(
            "Starting Packing MCP server (transport=%s, api=%s, token=%s, printer=%s)",
            args.transport,
            settings.api_url,
            "set" if settings.access_token else "missing",
            settings.printer or "CUPS default",
        )
        try:
            server.run(transport="streamable-http" if args.transport == "streamable-http" else "stdio")
        except KeyboardInterrupt:
            return 0
        return 0

    client = PackingClient(settings)
    if command == "sync-once":
        try:
            asyncio.run(sync_once(client))
        except PackingError as exc:
            logger.error("Allegro sync failed: %s", exc)
            return 1
        return 0

    if args.interval <= 0:
        logger.error("--interval must be greater than zero")
        return 2
    if args.iterations is not None and args.iterations < 1:
        logger.error("--iterations must be at least 1")
        return 2
    logger.info(
        "Starting Allegro sync loop (interval=%ss, api=%s)", args.interval, settings.api_url,
    )
    try:
        return asyncio.run(run_loop(client, args.interval, max_iterations=args.iterations))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
