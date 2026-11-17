"""SQLite storage for Slate facts.

Connections are short-lived so several agent processes can share one file.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

MAX_TEXT_LENGTH = 16_000
MAX_QUERY_LENGTH = 1_000
MAX_TAG_LENGTH = 64
MAX_TAGS = 16
MAX_TTL_HOURS = 24 * 366
MAX_LIMIT = 100
DEFAULT_LIMIT = 20

# Parents we must never chmod. A database file inside them is still mode 0600.
_SHARED_DIRECTORIES = frozenset(
    {
        Path("/"),
        Path("/tmp"),
        Path("/var"),
        Path("/var/tmp"),
        Path("/dev/shm"),
        Path("/home"),
    }
)


@dataclass(frozen=True)
class Fact:
    id: int
    text: str
    tags: str | None
    created_at: str


class Database:
    """One SQLite file. Each method opens a connection, works, and closes it."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser().resolve()

    @classmethod
    def from_env(cls) -> Database:
        raw = os.environ.get("SLATE_DB", "").strip()
        if raw:
            return cls(raw)
        return cls(Path.home() / ".slate" / "slate.db")

    def write(self, text: str, tags: str | None = None, ttl_hours: int | None = None) -> int:
        body = _check_text(text)
        labels = _check_tags(tags)
        ttl = _check_ttl(ttl_hours)
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM facts WHERE expires_at IS NOT NULL AND expires_at <= datetime('now')"
            )
            if ttl is None:
                cursor = conn.execute(
                    "INSERT INTO facts (text, tags, expires_at) VALUES (?, ?, NULL)",
                    (body, labels),
                )
            else:
                # Bind only the modifier. SQLite then evaluates datetime().
                # Binding the text "datetime('now', ...)" stores that text, and the
                # later comparison never treats the row as expired.
                cursor = conn.execute(
                    "INSERT INTO facts (text, tags, expires_at) VALUES (?, ?, datetime('now', ?))",
                    (body, labels, f"+{ttl} hours"),
                )
            fact_id = cursor.lastrowid
        if fact_id is None:
            raise RuntimeError("insert did not return an id")
        return int(fact_id)

    def query(
        self,
        q: str | None = None,
        tags: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> list[Fact]:
        keyword = _check_query(q)
        labels = _check_tags(tags)
        row_limit = _check_limit(limit)
        sql = (
            "SELECT id, text, tags, created_at FROM facts "
            "WHERE (expires_at IS NULL OR expires_at > datetime('now'))"
        )
        params: list[object] = []
        if keyword is not None:
            sql += " AND text LIKE ? ESCAPE '\\'"
            params.append(f"%{_escape_like(keyword)}%")
        if labels is not None:
            for tag in labels.split(","):
                sql += " AND (',' || tags || ',') LIKE ? ESCAPE '\\'"
                params.append(f"%,{_escape_like(tag)},%")
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(row_limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_fact(row) for row in rows]

    def list_recent(self, limit: int = DEFAULT_LIMIT) -> list[Fact]:
        return self.query(limit=limit)

    def delete(self, fact_id: int) -> bool:
        fact_id = _check_fact_id(fact_id)
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            return cursor.rowcount > 0

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self.path.exists() and self.path.is_dir():
            raise ValueError(f"database path is a directory: {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5.0, isolation_level="DEFERRED")
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
                """
            )
            self._protect()
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
            self._protect()

    def _protect(self) -> None:
        _private_mode(self.path.parent, 0o700)
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{self.path}{suffix}")
            if candidate.exists():
                _private_mode(candidate, 0o600)


def _fact(row: sqlite3.Row) -> Fact:
    created = row["created_at"]
    return Fact(
        id=int(row["id"]),
        text=str(row["text"]),
        tags=row["tags"],
        created_at="" if created is None else str(created),
    )


def _private_mode(path: Path, mode: int) -> None:
    try:
        stat = path.stat()
    except OSError:
        return
    if stat.st_uid != os.getuid():
        return
    if path.is_dir():
        resolved = path.resolve()
        home = Path.home().resolve()
        if resolved in _SHARED_DIRECTORIES or resolved == home:
            return
    os.chmod(path, mode)


def _check_text(text: object) -> str:
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("text must not be empty")
    if "\x00" in cleaned:
        raise ValueError("text must not contain NUL")
    if len(cleaned) > MAX_TEXT_LENGTH:
        raise ValueError(f"text must be at most {MAX_TEXT_LENGTH} characters")
    return cleaned


def _check_query(q: object) -> str | None:
    if q is None:
        return None
    if not isinstance(q, str):
        raise ValueError("q must be a string")
    if "\x00" in q:
        raise ValueError("q must not contain NUL")
    cleaned = q.strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_QUERY_LENGTH:
        raise ValueError(f"q must be at most {MAX_QUERY_LENGTH} characters")
    return cleaned


def _check_tags(tags: object) -> str | None:
    if tags is None:
        return None
    if not isinstance(tags, str):
        raise ValueError("tags must be a string")
    if "\x00" in tags:
        raise ValueError("tags must not contain NUL")
    labels: list[str] = []
    for raw in tags.split(","):
        label = raw.strip()
        if not label:
            continue
        if any(ch.isspace() and ch != " " for ch in label):
            raise ValueError("tags must not contain newlines")
        if len(label) > MAX_TAG_LENGTH:
            raise ValueError(f"each tag must be at most {MAX_TAG_LENGTH} characters")
        if label not in labels:
            labels.append(label)
    if not labels:
        return None
    if len(labels) > MAX_TAGS:
        raise ValueError(f"a fact may have at most {MAX_TAGS} tags")
    return ",".join(labels)


def _check_ttl(ttl_hours: object) -> int | None:
    if ttl_hours is None:
        return None
    if type(ttl_hours) is not int:
        raise ValueError("ttl_hours must be an integer number of hours")
    if not 1 <= ttl_hours <= MAX_TTL_HOURS:
        raise ValueError(f"ttl_hours must be between 1 and {MAX_TTL_HOURS}")
    return ttl_hours


def _check_limit(limit: object) -> int:
    if type(limit) is not int:
        raise ValueError("limit must be an integer")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    return limit


def _check_fact_id(fact_id: object) -> int:
    if type(fact_id) is not int or fact_id < 1:
        raise ValueError("fact_id must be a positive integer")
    return fact_id


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
