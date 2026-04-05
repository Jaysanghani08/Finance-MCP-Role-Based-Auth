# PS2 MCP Server — Portfolio Risk & Alert Monitor

### Only For Educational Purposes

Production-grade MCP server for AI League #3 Use Case 2 (Portfolio Risk & Alert Monitor).

## What this repo provides

- **21 MCP tools**, 5 resources, 3 prompts for portfolio risk monitoring.
- **HTTP transport** via [FastMCP 3.x](https://gofastmcp.com/getting-started/quickstart).
- **Auth0 OAuth 2.1 + PKCE** via FastMCP's OIDC proxy — clients discover OAuth endpoints automatically, open Auth0 login in the browser, and receive a token.
- **RFC 9728** Protected Resource Metadata at `/.well-known/oauth-protected-resource`.
- **Tier-aware authorization** (`free`, `premium`, `analyst`) controls tool/resource/prompt visibility and access per-request.
- **Cross-source reasoning** combining 4+ upstream APIs with confirmation/contradiction analysis.
- **Health-check endpoint** at `/health` showing upstream API status and remaining quotas.
- Local persistence, TTL caching, rate limiting, and audit logging.
- **Docker + Docker Compose** for one-command deployment.

## Architecture

See `docs/architecture.md` for the full architecture diagram and component descriptions.

## Auth Model

- The server uses FastMCP's `OIDCProxy` which acts as an **OIDC proxy**: it exposes OAuth discovery metadata, handles dynamic client registration, and proxies the authorization code exchange to Auth0.
- MCP clients follow the standard OAuth 2.1 + PKCE flow — the user logs in via Auth0 in a browser, the client receives a token, and sends it with every MCP request.
- The custom claim `https://ps2.example.com/tier` determines the user tier. OAuth `scope` / `permissions` claims carry the scope set.
- FastMCP's authorization system gates each tool/resource/prompt so clients only see what their tier and scopes allow.
- Unauthenticated requests receive `401` with `WWW-Authenticate` header pointing to `/.well-known/oauth-protected-resource`.

## Prerequisites

- Python 3.11+
- Auth0 tenant with:
  - An **API** (audience) configured
  - A **Regular Web Application** (not SPA) — needed for the client secret
  - Access tokens include custom claim `https://ps2.example.com/tier`

## Auth0 Application Setup

1. Go to **Applications > Applications** in your Auth0 dashboard
2. Click **Create Application** > choose **Regular Web Applications**
3. In **Settings**:
  - Copy the **Client ID** and **Client Secret**
  - Under **Allowed Callback URLs** add: `http://localhost:8000/auth/callback`
4. Save
5. Go to **Applications > APIs**, find your API, and copy the **Identifier** (audience)

## Setup

1. Copy env:
  ```bash
   cp .env.example .env
  ```
2. Fill in `.env` (see `.env.example` for sign-up links):
  - `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, `AUTH0_ISSUER`
  - `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`
  - Optional: `NEWS_API_KEY`, `ALPHA_VANTAGE_API_KEY`, `DATA_GOV_API_KEY`
3. Install:
  ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
  ```

## Running the Server

```bash
ps2-mcp-server
```

Or via FastMCP CLI:

```bash
fastmcp run app/ps2_fastmcp.py:mcp --transport http --port 8000
```

The server starts on `http://0.0.0.0:8000/mcp`.

### Docker

```bash
# One-command start
docker compose up --build

# Or build and run manually
docker build -t ps2-mcp-server .
docker run -p 8000:8000 --env-file .env ps2-mcp-server
```

### Health Check

```bash
curl http://localhost:8000/health
```

Returns upstream API status, remaining quotas, and server version.

## Cursor Setup

Configure `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ps2-mcp": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Restart MCP servers in Cursor. On first connection, Cursor will open your Auth0 login page in the browser. After login, Cursor receives a token automatically.

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Key Files


| File                            | Description                                                                              |
| ------------------------------- | ---------------------------------------------------------------------------------------- |
| `app/ps2_fastmcp.py`            | FastMCP HTTP server: Auth0 OIDC proxy, tools, resources, prompts, health check, RFC 9728 |
| `app/core/contracts.py`         | Tool/resource/prompt scope + tier contracts                                              |
| `app/services/mcp_service.py`   | Business logic orchestration                                                             |
| `app/services/risk_engine.py`   | Cross-source analysis engine with confirmation/contradiction patterns                    |
| `app/auth/access_control.py`    | Tier + scope enforcement                                                                 |
| `app/adapters/`                 | Upstream API clients (Yahoo Finance, NewsAPI, MFapi.in, RBI)                             |
| `docs/architecture.md`          | Architecture diagram                                                                     |
| `docs/technical_explanation.md` | Technical design decisions                                                               |
| `docs/schema_reference.md`      | Complete API reference (tools, resources, prompts, scopes)                               |
| `docs/scope_tier_matrix.md`     | Tier → scope matrix                                                                      |
| `Dockerfile`                    | Container image                                                                          |
| `docker-compose.yml`            | One-command deployment                                                                   |
| `tests/`                        | Unit tests for contracts, risk engine, rate limiter                                      |


## Demo Scenarios

### Must-Show Auth Boundary

1. **Free user** adds portfolio and sees basic summary → attempts `portfolio_risk_report` → receives `insufficient_scope` error
2. **Premium user** runs health check and MF overlap → attempts `what_if_analysis` → receives `insufficient_scope` error
3. **Analyst** gets everything including `what_if_analysis` and full cross-source risk reports

### Must-Show Cross-Source Moment

`portfolio_risk_report` combines:

- Current prices [NSE/yfinance]
- Sector mapping [derived from holdings]
- Macro indicators [RBI DBIE]
- News sentiment [NewsAPI]
- MF overlap [MFapi.in]

Into a single coherent risk narrative with explicit confirmations and contradictions, each citing which sources confirmed or contradicted the finding.