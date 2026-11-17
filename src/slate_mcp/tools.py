"""MCP tools for the shared blackboard.

The tools check inputs and format replies. SQLite stays in the database layer.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from slate_mcp.db import Database, Fact


def register_tools(server: MCPServer, db: Database) -> None:
    @server.tool()
    def write(text: str, tags: str | None = None, ttl_hours: int | None = None) -> str:
        """Store a fact on the shared blackboard.

        text is required. tags is an optional comma-separated list.
        ttl_hours is an optional lifetime in whole hours. Omit it to keep the fact until it is deleted.
        """
        fact_id = _run(lambda: db.write(text, tags, ttl_hours))
        return f"Stored fact {fact_id}"

    @server.tool()
    def query(q: str | None = None, tags: str | None = None, limit: int = 20) -> str:
        """Search facts that have not expired.

        q matches the fact text. tags is a comma-separated list and every tag must match.
        limit defaults to 20.
        """
        facts = _run(lambda: db.query(q, tags, limit))
        return _format(facts, "No matching facts.")

    @server.tool(name="list")
    def list_facts(limit: int = 20) -> str:
        """List the most recent facts that have not expired.

        limit defaults to 20.
        """
        facts = _run(lambda: db.list_recent(limit))
        return _format(facts, "No facts yet.")

    @server.tool()
    def delete(fact_id: int) -> str:
        """Delete a fact by its id."""
        removed = _run(lambda: db.delete(fact_id))
        if removed:
            return f"Deleted fact {fact_id}"
        return f"No fact with id {fact_id}"


def _format(facts: list[Fact], empty: str) -> str:
    if not facts:
        return empty
    return "\n".join(
        f"[{fact.id}] {fact.text} (tags: {fact.tags or '-'})" for fact in facts
    )


def _run[T](action: Callable[[], T]) -> T:
    try:
        return action()
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    except sqlite3.OperationalError as exc:
        lowered = str(exc).lower()
        if "locked" in lowered or "busy" in lowered:
            raise ToolError("The blackboard database is busy. Retry the tool call.") from exc
        raise ToolError(f"The blackboard database could not be updated: {exc}") from exc
