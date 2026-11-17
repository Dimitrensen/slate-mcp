"""Tool-layer tests against an in-process MCP server."""

from __future__ import annotations

import asyncio
from pathlib import Path

from mcp import Client

from slate_mcp.db import Database
from slate_mcp.server import create_server


def _text(result: object) -> str:
    assert getattr(result, "is_error", False) is False
    return "\n".join(
        block.text for block in result.content if getattr(block, "type", None) == "text"  # type: ignore[attr-defined]
    )


def test_tools_write_query_and_delete(tmp_path: Path) -> None:
    asyncio.run(_tools_write_query_and_delete(tmp_path))


async def _tools_write_query_and_delete(tmp_path: Path) -> None:
    db = Database(tmp_path / "board" / "slate.db")
    server = create_server(db)
    async with Client(server, read_timeout_seconds=30) as client:
        stored = _text(await client.call_tool("write", {"text": "from the tool", "tags": "demo"}))
        assert stored == "Stored fact 1"
        found = _text(await client.call_tool("query", {"q": "tool", "tags": "demo"}))
        assert found == "[1] from the tool (tags: demo)"
        listed = _text(await client.call_tool("list", {}))
        assert "from the tool" in listed
        assert _text(await client.call_tool("delete", {"fact_id": 1})) == "Deleted fact 1"
        assert _text(await client.call_tool("query", {"q": "tool"})) == "No matching facts."


def test_empty_text_is_a_tool_error(tmp_path: Path) -> None:
    asyncio.run(_empty_text_is_a_tool_error(tmp_path))


async def _empty_text_is_a_tool_error(tmp_path: Path) -> None:
    server = create_server(Database(tmp_path / "board" / "slate.db"))
    async with Client(server, read_timeout_seconds=30) as client:
        result = await client.call_tool("write", {"text": "  "})
    assert result.is_error is True
    assert "empty" in result.content[0].text
