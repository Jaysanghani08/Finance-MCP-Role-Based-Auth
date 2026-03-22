# Technical Explanation

## MCP Primitive Design

- **Tools** handle imperative actions or computed analytics (`add_to_portfolio`, `portfolio_risk_report`).
- **Resources** represent stateful entities and snapshots (`portfolio://{user_id}/alerts`, `macro://snapshot`).
- **Prompts** are packaged multi-step compositions (`morning_risk_brief`, `rebalance_suggestions`).

This separation keeps server outputs structured JSON while allowing MCP clients to render narratives.

## OAuth 2.1 + PKCE Resource-Server Integration

- Auth server is Auth0 (external authorization server).
- MCP server validates bearer tokens via Auth0 JWKS:
  - signature
  - expiry
  - issuer
  - audience
  - scopes
- Unauthenticated calls return `401` with `WWW-Authenticate` including resource metadata discovery URL.
- Authenticated but under-scoped calls return `403` with `insufficient_scope`.

## Tier-Based Access Control

- Tiers: `free`, `premium`, `analyst`.
- Tier comes from custom claim: `https://ps2.example.com/tier`.
- Enforcement happens at operation boundary:
  - capability discovery (`/mcp/capabilities`) is tier-aware and scope-aware
  - tool/resource/prompt invocation checks both tier and scope

## Upstream Integration + Key Isolation

- Upstream adapters:
  - market
  - news/sentiment
  - macro
  - mutual funds
- API keys are read from server-side env and never sent to clients.
- Adapter responses are normalized into internal canonical structures consumed by risk logic.

## Caching, Rate Limiting, and Quota Management

- TTL cache by data type:
  - market snapshots: ~60s
  - news/sentiment: ~30 min
  - MF NAV: ~30 min
- User-level tier limits:
  - Free: 30/hour
  - Premium: 150/hour
  - Analyst: 500/hour
- `429` responses include `Retry-After`.
- Upstream quota manager tracks free-tier provider budgets and enables graceful degradation.

## Cross-Source Reasoning

- `portfolio_risk_report` combines:
  - current prices and allocations
  - concentration/sector exposure
  - MF overlap
  - macro indicators
  - sentiment shift
- Output explicitly includes:
  - confirmations (with source groups and evidence)
  - contradictions (with source groups and evidence)
  - citations per source

## Security and Audit

- Audience binding prevents token replay for wrong resource.
- Scope checks are operation-specific.
- API keys remain server-side only.
- Audit log records user, tier, operation, timestamp, and outcome for every tool execution.
