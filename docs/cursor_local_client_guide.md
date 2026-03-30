# Cursor Local MCP Client Guide (stdio + Auth0)

This guide shows how to connect Cursor to the PS2 MCP server through the `stdio` transport using real Auth0-backed authentication.

## 1) Prerequisites

- Python 3.11+
- Local repo checkout
- Auth0 Application configured as public client with Device Code grant enabled
- Auth0 API identifier matching `AUTH0_AUDIENCE`

## 2) Install project

From the repo root:

```bash
pip install -e .
```

## 3) Configure Auth0 values

Set these values in `.env` or pass them in Cursor `env`:

- `AUTH0_DOMAIN`
- `AUTH0_AUDIENCE`
- `AUTH0_ISSUER`
- `AUTH0_CLIENT_ID`

Optional scope override:

- `MCP_AUTH0_SCOPES` as a space-separated scope string.

## 4) Add MCP server in Cursor

Edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ps2-mcp": {
      "command": "ps2-mcp-stdio",
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

Alternative command form (without script install):

```json
{
  "mcpServers": {
    "ps2-mcp": {
      "command": "python3",
      "args": ["-m", "app.stdio_server"],
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

## 5) Validate tier behavior

After device login completes, tier/scope comes from token claims:

- Free tier:
  - `get_portfolio_summary` should work.
  - `portfolio_risk_report` should fail with insufficient scope/tier.
- Premium tier:
  - `portfolio_health_check` should work.
  - `what_if_analysis` should fail.
- Analyst tier:
  - `portfolio_risk_report` and `what_if_analysis` should work.

## 6) Troubleshooting

- **Server not starting**: Re-run `pip install -e .` and verify `ps2-mcp-stdio` exists in your shell path.
- **No tools shown in Cursor**: Reload Cursor window after editing `mcp.json`.
- **Auth prompt never appears**: Check terminal logs for `Authenticate at:` URL from `ps2-mcp-stdio`.
- **Login denied/expired**: Restart MCP server and complete Auth0 device login before code expires.
- **`unauthorized_client` for device flow**: In Auth0 Application settings, enable the Device Code grant type.
- **Wrong capability set**: Verify token has expected tier claim `https://ps2.example.com/tier` and required scopes.
