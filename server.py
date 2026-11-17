#!/usr/bin/env python3
"""Slate – Shared blackboard MCP server."""

import os
import sqlite3
from pathlib import Path
from typing import Optional

from mcp.server import MCPServer

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DB_PATH = Path(os.environ.get("SLATE_DB", Path.home() / ".slate" / "slate.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP
        )
    """)
    conn.commit()
    return conn

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = MCPServer(
    "Slate",
    instructions="Shared blackboard. Write facts, query them, list recent ones, or delete by id."
)

@mcp.tool()
def write(text: str, tags: Optional[str] = None, ttl_hours: Optional[int] = None) -> str:
    """Store a fact on the shared blackboard.

    Args:
        text: The fact to store.
        tags: Optional comma-separated tags.
        ttl_hours: Optional time-to-live in hours.
    """
    conn = get_db()
    expires = None
    if ttl_hours:
        expires = f"datetime('now', '+{ttl_hours} hours')"
    conn.execute(
        "INSERT INTO facts (text, tags, expires_at) VALUES (?, ?, ?)",
        (text, tags, expires)
    )
    conn.commit()
    fact_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return f"Stored fact {fact_id}"

@mcp.tool()
def query(q: Optional[str] = None, tags: Optional[str] = None, limit: int = 20) -> str:
    """Search facts by keyword or tags.

    Args:
        q: Optional keyword to search in the text.
        tags: Optional comma-separated tags (all must match).
        limit: Max results (default 20).
    """
    conn = get_db()
    sql = "SELECT id, text, tags, created_at FROM facts WHERE (expires_at IS NULL OR expires_at > datetime('now'))"
    params = []
    if q:
        sql += " AND text LIKE ?"
        params.append(f"%{q}%")
    if tags:
        for tag in [t.strip() for t in tags.split(",") if t.strip()]:
            sql += " AND tags LIKE ?"
            params.append(f"%{tag}%")
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return "No matching facts."
    return "\n".join(f"[{r['id']}] {r['text']} (tags: {r['tags'] or '-'})" for r in rows)

@mcp.tool()
def list_facts(limit: int = 20) -> str:
    """List the most recent facts.

    Args:
        limit: Max results (default 20).
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT id, text, tags, created_at FROM facts "
        "WHERE (expires_at IS NULL OR expires_at > datetime('now')) "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    if not rows:
        return "No facts yet."
    return "\n".join(f"[{r['id']}] {r['text']} (tags: {r['tags'] or '-'})" for r in rows)

@mcp.tool()
def delete(fact_id: int) -> str:
    """Delete a fact by its id.

    Args:
        fact_id: The id of the fact to delete.
    """
    conn = get_db()
    cur = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
    conn.commit()
    if cur.rowcount:
        return f"Deleted fact {fact_id}"
    return f"No fact with id {fact_id}"

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()  # stdio transport