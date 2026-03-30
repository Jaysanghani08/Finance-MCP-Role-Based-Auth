# PS2 MCP Server (stdio + Auth0)

Production-style MCP server for AI League #3 Use Case 2 (Portfolio Risk & Alert Monitor).

## What this repo provides

- MCP tools/resources/prompts for PS2.
- Tier-aware authorization (`free`, `premium`, `analyst`) based on Auth0 JWT claims.
- Auth0-backed login using Device Authorization flow in the stdio server.
- Local persistence, caching, rate limiting, and audit logging.

## Prerequisites

- Python 3.11+
- Auth0 tenant + API + public client
- Auth0 access token includes custom claim `https://ps2.example.com/tier`

## Setup

1. Copy env:
  - `cp .env.example .env`
2. Fill in:
  - `AUTH0_DOMAIN`
  - `AUTH0_AUDIENCE`
  - `AUTH0_ISSUER`
  - `AUTH0_CLIENT_ID`
3. Install:
  - `python3 -m venv .venv`
  - `source .venv/bin/activate`
  - `pip install -e .`

## Cursor setup

Configure `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ps2-mcp": {
      "command": "/ABSOLUTE/PATH/TO/Week-3/.venv/bin/ps2-mcp-stdio",
      "env": {
        "AUTH0_DOMAIN": "your-tenant.us.auth0.com",
        "AUTH0_AUDIENCE": "https://ps2-mcp-api",
        "AUTH0_ISSUER": "https://your-tenant.us.auth0.com/",
        "AUTH0_CLIENT_ID": "your_auth0_client_id"
      }
    }
  }
}
```

Restart MCP servers in Cursor. The server prints an Auth0 activation URL and code; complete login once prompted.

## Optional env

- `MCP_AUTH0_SCOPES` (space-separated scopes override for device flow request).

## Key files

- `app/stdio_server.py` - MCP stdio transport and Auth0 device flow auth.
- `app/core/contracts.py` - tool/resource/prompt scope+tier contracts.
- `app/services/mcp_service.py` - business logic orchestration.
- `docs/scope_tier_matrix.md` - tier matrix.
- `docs/schema_reference.md` - schemas.

