"""Build the Slate MCP server."""

from __future__ import annotations

from mcp.server import MCPServer

from slate_mcp import __version__
from slate_mcp.db import Database
from slate_mcp.tools import register_tools


def create_server(db: Database | None = None) -> MCPServer:
    database = db if db is not None else Database.from_env()
    server = MCPServer(
        "Slate",
        instructions=(
            "Shared blackboard. Write facts, query them, list recent ones, or delete by id. "
            "Every client that uses this database sees the same facts."
        ),
        version=__version__,
        log_level="WARNING",
    )
    register_tools(server, database)
    return server
