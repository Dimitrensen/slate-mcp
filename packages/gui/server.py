"""Local window onto the Slate board.

Reads the same SQLite file the chats use and only listens on this machine.
From the repository root:

    uv run python packages/gui/server.py

Then open http://127.0.0.1:8766/
The port can be changed with SLATE_GUI_PORT. The file can be changed with SLATE_DB.
"""

from __future__ import annotations

import html
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from slate_mcp.db import MAX_LIMIT, Database

DEFAULT_PORT = 8766
_HOST = "127.0.0.1"


def main() -> None:
    database = Database.from_env()
    port = _port()
    server = ThreadingHTTPServer((_HOST, port), _handler(database))
    print(f"Slate board at http://{_HOST}:{port}/", flush=True)
    print(f"Reading {database.path}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    finally:
        server.server_close()


def _port() -> int:
    raw = os.environ.get("SLATE_GUI_PORT", "").strip()
    if not raw:
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError as exc:
        raise SystemExit("SLATE_GUI_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("SLATE_GUI_PORT must be between 1 and 65535")
    return port


def _handler(database: Database) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] != "/":
                self.send_error(404)
                return
            body = _page(database).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    return Handler


def _page(database: Database) -> str:
    facts = database.list_recent(MAX_LIMIT)
    path = html.escape(str(database.path))
    if not facts:
        rows = '<p class="empty">No notes yet.</p>'
    else:
        rendered = []
        for fact in facts:
            tags = html.escape(fact.tags) if fact.tags else "—"
            rendered.append(
                "<tr>"
                f"<td>{fact.id}</td>"
                f"<td>{html.escape(fact.text)}</td>"
                f"<td>{tags}</td>"
                f"<td>{html.escape(fact.created_at)}</td>"
                "</tr>"
            )
        rows = (
            "<table><thead><tr><th>Id</th><th>Note</th><th>Tags</th><th>Written</th></tr></thead>"
            f"<tbody>{''.join(rendered)}</tbody></table>"
        )
    count = len(facts)
    noun = "note" if count == 1 else "notes"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Slate</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0;
    font: 16px/1.45 Georgia, "Iowan Old Style", Palatino, serif;
    color: #1c1915;
    background: #f6f3ec;
  }}
  main {{ max-width: 46rem; margin: 0 auto; padding: 2.5rem 1.25rem 3rem; }}
  h1 {{ font-size: 1.6rem; font-weight: 600; margin: 0 0 0.25rem; }}
  p {{ margin: 0.35rem 0; }}
  .meta {{ color: #5c564c; font: 0.85rem/1.4 ui-sans-serif, system-ui, sans-serif; }}
  .path {{ word-break: break-all; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1.5rem; }}
  th, td {{ text-align: left; vertical-align: top; padding: 0.55rem 0.6rem; border-bottom: 1px solid #ddd6c8; }}
  th {{ font: 0.75rem/1.2 ui-sans-serif, system-ui, sans-serif; letter-spacing: 0.04em; text-transform: uppercase; color: #5c564c; }}
  td:first-child {{ width: 2.5rem; color: #5c564c; }}
  .empty {{ margin-top: 1.5rem; }}
</style>
</head>
<body>
<main>
  <h1>Slate</h1>
  <p class="meta">{count} {noun} on this board. Reload the page to read the file again.</p>
  <p class="meta path">{path}</p>
  {rows}
</main>
</body>
</html>
"""


if __name__ == "__main__":
    main()
