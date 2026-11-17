"""Database tests: write, query, expiry, validation, and file permissions."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from slate_mcp.db import MAX_TEXT_LENGTH, MAX_TTL_HOURS, Database


def _open(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path)


def _expire(db: Database, fact_id: int) -> None:
    conn = _open(db.path)
    try:
        conn.execute(
            "UPDATE facts SET expires_at = datetime('now', '-1 minute') WHERE id = ?",
            (fact_id,),
        )
        conn.commit()
    finally:
        conn.close()


def _expires_at(db: Database, fact_id: int) -> str | None:
    conn = _open(db.path)
    try:
        row = conn.execute("SELECT expires_at FROM facts WHERE id = ?", (fact_id,)).fetchone()
    finally:
        conn.close()
    assert row is not None
    return row[0]


def test_write_query_and_list_round_trip(tmp_path: Path) -> None:
    db = Database(tmp_path / "board" / "slate.db")
    first = db.write("tower fan is quiet", "infra")
    second = db.write("cluster is online", "infra,pi")

    assert [fact.id for fact in db.list_recent()] == [second, first]
    matches = db.query(q="cluster", tags="pi")
    assert [fact.text for fact in matches] == ["cluster is online"]
    assert matches[0].tags == "infra,pi"


def test_ttl_is_evaluated_in_sql(tmp_path: Path) -> None:
    db = Database(tmp_path / "board" / "slate.db")
    fact_id = db.write("temporary note", None, 2)
    stored = _expires_at(db, fact_id)
    assert stored is not None
    assert "datetime" not in stored

    conn = _open(db.path)
    try:
        delta = conn.execute(
            "SELECT CAST((julianday(expires_at) - julianday('now')) * 24 AS REAL) FROM facts WHERE id = ?",
            (fact_id,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert 1.9 <= delta <= 2.1

    kept = db.write("kept", None, None)
    assert _expires_at(db, kept) is None


def test_expired_fact_is_hidden_and_removed_on_next_write(tmp_path: Path) -> None:
    db = Database(tmp_path / "board" / "slate.db")
    gone = db.write("gone soon", "temp", 1)
    _expire(db, gone)

    assert db.query(q="gone") == []
    assert db.list_recent() == []
    assert _expires_at(db, gone) is not None

    db.write("stays", None, None)
    conn = _open(db.path)
    try:
        texts = [row[0] for row in conn.execute("SELECT text FROM facts ORDER BY id")]
    finally:
        conn.close()
    assert texts == ["stays"]


def test_tag_match_is_whole_tag(tmp_path: Path) -> None:
    db = Database(tmp_path / "board" / "slate.db")
    db.write("short", "infra")
    db.write("long", "infrastructure")
    db.write("both", "infra,pi")

    assert [fact.text for fact in db.query(tags="infra")] == ["both", "short"]
    assert [fact.text for fact in db.query(tags="infra,pi")] == ["both"]


def test_like_wildcards_are_literal(tmp_path: Path) -> None:
    db = Database(tmp_path / "board" / "slate.db")
    db.write("100% done", None)
    db.write("axb", None)
    db.write("a_b", None)

    assert [fact.text for fact in db.query(q="%")] == ["100% done"]
    assert [fact.text for fact in db.query(q="a_b")] == ["a_b"]


def test_sql_text_is_stored_as_data(tmp_path: Path) -> None:
    db = Database(tmp_path / "board" / "slate.db")
    payload = "it's a fact'); DROP TABLE facts;--"
    db.write(payload, None)
    assert db.query(q="DROP TABLE")[0].text == payload
    db.write("still here", None)
    assert [fact.text for fact in db.list_recent()] == ["still here", payload]


def test_delete(tmp_path: Path) -> None:
    db = Database(tmp_path / "board" / "slate.db")
    fact_id = db.write("remove me", None)
    assert db.delete(fact_id) is True
    assert db.delete(fact_id) is False
    assert db.list_recent() == []


def test_rejects_bad_input(tmp_path: Path) -> None:
    db = Database(tmp_path / "board" / "slate.db")
    with pytest.raises(ValueError, match="empty"):
        db.write("   ", None)
    with pytest.raises(ValueError, match="characters"):
        db.write("x" * (MAX_TEXT_LENGTH + 1), None)
    with pytest.raises(ValueError, match="integer"):
        db.write("ok", None, True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="between"):
        db.write("ok", None, 0)
    with pytest.raises(ValueError, match="between"):
        db.write("ok", None, MAX_TTL_HOURS + 1)
    with pytest.raises(ValueError, match="limit"):
        db.list_recent(0)
    with pytest.raises(ValueError, match="positive"):
        db.delete(0)


def test_database_file_is_private(tmp_path: Path) -> None:
    db = Database(tmp_path / "board" / "slate.db")
    db.write("secret", None)
    assert db.path.stat().st_mode & 0o777 == 0o600
    assert db.path.parent.stat().st_mode & 0o777 == 0o700
    for suffix in ("-wal", "-shm"):
        side = Path(f"{db.path}{suffix}")
        if side.exists():
            assert side.stat().st_mode & 0o777 == 0o600


def test_shared_parent_directory_is_not_chmodded() -> None:
    parent = Path("/tmp")
    before = parent.stat().st_mode & 0o7777
    path = parent / f"slate-mcp-perm-{os.getpid()}.db"
    try:
        db = Database(path)
        db.write("x", None)
        assert parent.stat().st_mode & 0o7777 == before
        assert path.stat().st_mode & 0o777 == 0o600
    finally:
        for suffix in ("", "-wal", "-shm"):
            Path(f"{path}{suffix}").unlink(missing_ok=True)
