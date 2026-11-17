"""Process entry point for `slate` and `slate-mcp`."""

from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    from slate_mcp.server import create_server

    server = create_server()
    if args.transport == "stdio":
        server.run(transport="stdio")
        return

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print(
            "Slate SSE has no authentication. "
            f"Binding to {args.host} lets anyone who can open the port read, write, and delete every fact.",
            file=sys.stderr,
        )
    server.run(transport="sse", host=args.host, port=args.port)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="slate",
        description="Shared blackboard MCP server.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse"),
        default=os.environ.get("SLATE_TRANSPORT", "stdio"),
        help="stdio (default) or sse. SLATE_TRANSPORT overrides the default.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("SLATE_HOST", "127.0.0.1"),
        help="SSE bind address. Default 127.0.0.1. SLATE_HOST overrides the default.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_port_default(),
        help="SSE port. Default 8765. SLATE_PORT overrides the default.",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if not args.host or any(ch.isspace() for ch in args.host):
        parser.error("host must be a hostname or IP address without spaces")
    return args


def _port_default() -> int:
    raw = os.environ.get("SLATE_PORT")
    if raw is None or raw.strip() == "":
        return 8765
    try:
        return int(raw)
    except ValueError as exc:
        raise SystemExit("SLATE_PORT must be an integer") from exc
