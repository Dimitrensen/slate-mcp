"""Two stdio processes share one database file."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

from slate_mcp.cli import main


def test_help_exits() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0


def test_bad_port_exits() -> None:
    with pytest.raises(SystemExit):
        main(["--port", "0"])


def test_console_scripts_point_at_cli() -> None:
    bindir = Path(sys.executable).parent
    for name in ("slate", "slate-mcp"):
        script = bindir / name
        assert script.is_file(), f"missing console script {script}"
        assert "slate_mcp.cli" in script.read_text(encoding="utf-8")


def test_two_stdio_clients_share_facts(tmp_path: Path) -> None:
    asyncio.run(_two_stdio_clients_share_facts(tmp_path / "slate.db"))


def _params(db_path: Path) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "slate_mcp"],
        env={
            "SLATE_DB": str(db_path),
            "HOME": str(Path.home()),
            "PATH": os.environ.get("PATH", ""),
            "PYTHONUNBUFFERED": "1",
        },
    )


def _text(result: object) -> str:
    assert getattr(result, "is_error", False) is False
    return "\n".join(
        block.text for block in result.content if getattr(block, "type", None) == "text"  # type: ignore[attr-defined]
    )


async def _two_stdio_clients_share_facts(db_path: Path) -> None:
    params = _params(db_path)
    async with (
        Client(params, read_timeout_seconds=60) as writer,
        Client(params, read_timeout_seconds=60) as reader,
    ):
        stored = _text(
            await writer.call_tool(
                "write",
                {"text": "cluster fan is quiet", "tags": "infra,pi", "ttl_hours": 24},
            )
        )
        assert stored.startswith("Stored fact ")
        fact_id = int(stored.rsplit(" ", 1)[1])

        found = _text(await reader.call_tool("query", {"q": "fan", "tags": "pi"}))
        assert f"[{fact_id}] cluster fan is quiet (tags: infra,pi)" in found

        listed = _text(await reader.call_tool("list", {"limit": 10}))
        assert "cluster fan is quiet" in listed

        assert _text(await reader.call_tool("delete", {"fact_id": fact_id})) == f"Deleted fact {fact_id}"
        assert _text(await writer.call_tool("query", {"q": "fan"})) == "No matching facts."
