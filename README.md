# Slate

Shared blackboard MCP server.  
Multiple agents can write and read the same facts without you copying context between them.

## What it does

Slate is a small, self-hosted MCP server that acts as a shared working memory for agents.  
One agent writes a fact, another agent queries it. No central orchestrator required.

## Tools (v0.1)

| Tool   | Description                          |
|--------|--------------------------------------|
| write  | Store a fact (text + optional tags + optional TTL) |
| query  | Search facts by keyword or tags      |
| list   | List recent facts                    |
| delete | Delete a fact by id                  |

## Quick start

### With uv
```bash
uv run slate
