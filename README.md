# Slate

Shared blackboard MCP server.
Multiple agents can write and read the same facts without you copying context between them.

## What it does

Slate is the terminal board: a small, self-hosted MCP server. One agent writes a fact. Another agent queries it.
The shared state is one SQLite file. Your own terminal client starts the server. Slate does not install a harness or an orchestrator.

## Tools

| Tool   | Description                                      |
|--------|--------------------------------------------------|
| write  | Store a fact (text, optional tags, optional TTL) |
| query  | Search facts by keyword or tags                  |
| list   | List recent facts                                |
| delete | Delete a fact by id                              |

A fact's text is at most 16000 characters. A fact has at most 16 tags.
`ttl_hours` is a whole number from 1 to 8784 (about one year). Omit it to keep the fact until it is deleted.
`list` and `query` return at most 100 rows. Expired facts disappear from both, and the next write removes them from the file.

## Quick start

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv run slate
```

`uv run slate-mcp` starts the same server. The default transport is stdio, which is what Claude Code and Cursor launch themselves.

The database file defaults to `$HOME/.slate/slate.db`. Override it with `SLATE_DB`.

```bash
SLATE_DB=/absolute/path/slate.db uv run slate
```

## Clients

Point every client at the same `SLATE_DB` and the same checkout.
Use absolute paths. A desktop app often does not inherit your shell `PATH`.

### Claude Code

Project scope is `.mcp.json` in the project you are working in.
User scope is the `mcpServers` object in `~/.claude.json`.

```json
{
  "mcpServers": {
    "slate": {
      "type": "stdio",
      "command": "/absolute/path/to/uv",
      "args": ["run", "--directory", "/absolute/path/to/slate-mcp", "slate"],
      "env": {
        "SLATE_DB": "/absolute/path/.slate/slate.db"
      }
    }
  }
}
```

Approve the server with `/mcp` in Claude Code the first time you use a project `.mcp.json`.

### Cursor

Global config is `~/.cursor/mcp.json`. Project config is `.cursor/mcp.json`.

```json
{
  "mcpServers": {
    "slate": {
      "type": "stdio",
      "command": "/absolute/path/to/uv",
      "args": ["run", "--directory", "/absolute/path/to/slate-mcp", "slate"],
      "env": {
        "SLATE_DB": "/absolute/path/.slate/slate.db"
      }
    }
  }
}
```

Restart Cursor after saving the file. A write from one client is then visible to a query from the other, because both processes open the same file.

### Pi

If you already run [Pi](https://pi.dev/), point it at the same command and the same `SLATE_DB`.
User scope is `~/.pi/agent/mcp.json`. Project scope is `.pi/mcp.json`, and Pi reads that file only after you trust the project.

```json
{
  "mcpServers": {
    "slate": {
      "command": "/absolute/path/to/uv",
      "args": ["run", "--directory", "/absolute/path/to/slate-mcp", "slate"],
      "env": {
        "SLATE_DB": "/absolute/path/.slate/slate.db"
      },
      "exposure": "direct"
    }
  }
}
```

`exposure` is `direct` so the four tools are offered to the model. Pi's default leaves MCP tools for its code-mode search to find.

The same entry from a shell:

```bash
pi mcp add slate --env SLATE_DB=/absolute/path/.slate/slate.db -- /absolute/path/to/uv run --directory /absolute/path/to/slate-mcp slate
```

Then run `pi mcp list`. Add `--local` to write `.pi/mcp.json` instead of the user file. Pi speaks stdio and Streamable HTTP. Use this stdio entry for Pi.

### Orca

If you already run [Orca](https://orca.dev/), point it at the same command and the same `SLATE_DB`.
Orca runs the agent programs you installed, each in its own git worktree. The facts stay in the Slate database. Give every agent Orca launches the Slate entry for that agent, using the same `uv` command, arguments, and `SLATE_DB` as the sections above.

Orca can also register servers under Settings → Integrations → MCP. Those tools show up inside agent CLIs that support MCP. Use the same command and the same `SLATE_DB` there. Repository MCP settings stay on the machine where you saved them.

### Optional SSE

Stdio is the normal setup. SSE is for a long-running process on the machine that holds the database.

```bash
uv run slate --transport sse --host 127.0.0.1 --port 8765
```

Claude Code:

```json
{
  "mcpServers": {
    "slate": {
      "type": "sse",
      "url": "http://127.0.0.1:8765/sse"
    }
  }
}
```

Cursor:

```json
{
  "mcpServers": {
    "slate": {
      "url": "http://127.0.0.1:8765/sse"
    }
  }
}
```

## Docker

The image is meant for a small ARM board like a Pi5(8 GB RAM).
The base image is multi-arch. Compose caps the container at 256 MB and half a CPU.
The SQLite file lives on a bind mount, default `./.slate-data`, which is gitignored.

Stdio, for a client that spawns the container:

```bash
docker compose --profile stdio run --rm -i slate
```

SSE on localhost only:

```bash
docker compose --profile sse up -d --build
```

That publishes `127.0.0.1:8765` and listens on port 8765 inside the container.
To share the host database with `uv run slate` clients, point the mount at the same directory:

```bash
SLATE_DATA="$HOME/.slate" docker compose --profile sse up -d --build
```

The container starts as root only long enough to make `/data` private, then the server runs as uid 1000.

## Security

Slate has no authentication. It is a local blackboard for agents you already trust.

- Stdio is not a network service. Your MCP client starts the process.
- The database file is created mode `0600`. Its directory is mode `0700` when that directory is not a shared system path such as your home directory or `/tmp`.
- Do not commit the database. It can contain anything an agent wrote. It is not a password store.
- SSE defaults to `127.0.0.1`. The Docker publish line is also localhost-only. Anyone who can open the port can read, write, and delete every fact. Do not publish it on `0.0.0.0`.
- Tool arguments are length-checked, and SQL values are bound parameters.

## Tests

```bash
uv run pytest
```
