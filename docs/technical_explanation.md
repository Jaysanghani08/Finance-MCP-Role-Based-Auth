# PS2 MCP Server — Technical Explanation

## 1. MCP Primitive Design Decisions

### Tools vs Resources vs Prompts

| Primitive | Design Rationale | Examples |
|-----------|-----------------|----------|
| **Tools** | Actions that compute or mutate state. Each call produces a fresh result with citations. Used for all data retrieval and analysis operations. | `get_stock_quote`, `portfolio_risk_report`, `what_if_analysis` |
| **Resources** | Read-only state snapshots scoped to a user or global context. Cached, subscribable for change notifications. Represent "current state" rather than computed analysis. | `portfolio://{user_id}/holdings`, `market://overview` |
| **Prompts** | Pre-composed analysis workflows that orchestrate multiple tools. Return structured data the client can render as a narrative. Named after the user intent they serve. | `morning_risk_brief`, `rebalance_suggestions` |

**Key decisions:**
- Portfolio management (`add_to_portfolio`, `remove_from_portfolio`) are tools because they mutate state.
- Portfolio holdings are also exposed as a resource for passive read access.
- `morning_risk_brief` is a prompt (not a tool) because it composes multiple tools into a single pre-defined workflow — the user asks "give me my morning brief" rather than choosing which sub-analyses to run.
- Cross-source reasoning tools (`portfolio_risk_report`, `what_if_analysis`) are tools rather than prompts because they accept parameters and produce structured analytical output, not pre-composed narratives.

### Subscription Model

FastMCP does not expose the legacy `resources/subscribe` / `resources/events` JSON-RPC methods. We register three utility tools (`ps2_resource_subscribe`, `ps2_resource_unsubscribe`, `ps2_resource_pull_events`) that wrap an in-memory pub/sub service. Resources marked `subscribable=True` in their contracts emit events when their underlying data changes (e.g., after a `portfolio_health_check` updates alerts).

## 2. OAuth 2.1 Implementation

### Auth Server Choice: Auth0

We use Auth0 as the external OAuth 2.1 authorization server. The MCP server acts as a **Resource Server** — it validates tokens but never issues them.

**Why Auth0:**
- Free tier sufficient for development and demo
- Built-in PKCE support for public clients
- Custom claims via Auth0 Actions (for the `tier` claim)
- JWKS endpoint for token signature verification
- Separate from MCP server (Resource Server pattern)

### PKCE Flow

FastMCP's `OIDCProxy` handles the PKCE authorization code flow:
1. Client discovers OAuth metadata via OIDC discovery
2. Client generates `code_verifier` and `code_challenge`
3. Authorization request includes `code_challenge_method=S256`
4. After user login, Auth0 returns an authorization code
5. Token exchange includes the `code_verifier` for server-side verification

### Token Validation

JWT tokens are validated at two levels:
1. **Transport level:** FastMCP's OIDC proxy validates the id_token signature, expiry, and issuer against Auth0's JWKS endpoint
2. **Application level:** The API access token is decoded (without re-verification, since the OIDC proxy already authenticated the session) to extract RBAC claims (`permissions`, `tier` custom claim)

The `_rbac_claims()` function merges claims from both the id_token and the API access token to build a complete `AuthContext`.

### RFC 9728 Protected Resource Metadata

The server exposes `/.well-known/oauth-protected-resource` which advertises:
- The resource server identifier
- The authorization server URL (Auth0 domain)
- All supported scopes
- Supported bearer token methods

Unauthenticated requests receive a `401` with a `WWW-Authenticate` header containing the `resource_metadata` URL, enabling automatic discovery.

## 3. Tier-Based Access Control

### Scope Definitions

| Scope | What It Controls |
|-------|-----------------|
| `market:read` | Live quotes, price history, indices, movers |
| `fundamentals:read` | Shareholding patterns |
| `technicals:read` | Technical indicators (reserved) |
| `mf:read` | Mutual fund NAV, search, overlap |
| `news:read` | News articles and sentiment |
| `filings:read` / `filings:deep` | Filing access (reserved) |
| `macro:read` | Current macro snapshot |
| `macro:historical` | Historical macro time series |
| `research:generate` | Cross-source reasoning tools |
| `portfolio:read` / `portfolio:write` | Portfolio holdings and analysis |

### Enforcement Points

1. **Visibility gate** (`_make_tier_auth_check`): Tools/resources/prompts are hidden from clients whose tier doesn't match `allowed_tiers`. A free user's client never sees `portfolio_risk_report` in tool discovery.

2. **Execution gate** (`enforce_contract_access`): Even if a client somehow invokes a tool, the handler checks `auth.tier in contract.allowed_tiers` and `all(scope in auth.scopes for scope in contract.required_scopes)`. Missing permissions raise `ForbiddenError` → MCP error code `-32003` with `"insufficient_scope"`.

3. **Rate limiting** (`RateLimiter.check`): Per-user, per-tier sliding window (1 hour). Exceeding the limit raises `RateLimitExceededError` → MCP error code `-32029` with `retry_after` seconds.

### Tier Matrix (PS2 Addendum)

| Capability | Free | Premium | Analyst |
|-----------|------|---------|---------|
| add/remove/summary | ✅ | ✅ | ✅ |
| health_check, concentration, overlap, macro, sentiment | ❌ | ✅ | ✅ |
| portfolio_risk_report, what_if_analysis | ❌ | ❌ | ✅ |
| Prompts (morning brief, rebalance, earnings) | ❌ | ✅ | ✅ |
| Resource subscriptions (alerts, risk_score) | ❌ | ✅ | ✅ |
| Rate limit | 30/hr | 150/hr | 500/hr |

## 4. Upstream API Integration

### Key Management

All upstream API keys are stored in the server's `.env` file and loaded via `pydantic-settings`. Keys are never exposed to MCP clients — the server makes upstream calls on behalf of users using its own credentials.

### Caching Strategy

| Data Type | TTL | Rationale |
|-----------|-----|-----------|
| Stock quotes | 60s | Prices are near-real-time but can tolerate brief staleness |
| News articles | 1800s (30 min) | News doesn't change frequently |
| Sentiment scores | 1800s (30 min) | Aggregated sentiment is stable short-term |
| Portfolio summary | 60s | Depends on live prices |
| Macro snapshot | 1800s (30 min) | RBI rates change infrequently |
| MF NAV | 1800s (30 min) | NAVs update once daily |

### Rate Limiting & Quota Management

- **User-tier limits:** Enforced per user via `RateLimiter` (sliding window, 1-hour granularity)
- **Upstream quotas:** `UpstreamQuotaManager` tracks calls to quota-limited APIs (NewsAPI: 100/day, Alpha Vantage: 25/day, Finnhub: 60/min). When a quota is exhausted, the tool returns a `degraded` response with cached/fallback data instead of failing.

### Graceful Degradation

Every adapter implements deterministic fallback:
- **MarketDataAdapter:** If Yahoo Finance returns an error, a hash-seeded deterministic quote is generated
- **NewsDataAdapter:** If NewsAPI fails or has no key, synthetic news items are generated
- **MacroDataAdapter:** If the RBI proxy is unreachable, cached reference values are returned
- **MutualFundAdapter:** If MFapi.in fails, a mock NAV is returned

Fallback responses always include a citation marking the data source as "fallback" or "deterministic" so the client and user can distinguish live vs cached data.

## 5. Cross-Source Reasoning

### How Signals Are Combined

The `portfolio_risk_report` tool (Analyst-only) executes five parallel analyses:

1. **Portfolio Summary** → prices from yfinance, sector allocation derived
2. **Concentration Risk** → stock/sector weight breaches (>20% stock, >40% sector)
3. **MF Overlap** → portfolio tickers vs popular large-cap fund holdings from MFapi.in
4. **Macro Sensitivity** → sector sensitivity model × current RBI/macro data
5. **Sentiment Shift** → 7-day vs 30-day sentiment delta per holding from NewsAPI

These are then cross-referenced to identify **confirmations** (multiple sources agree on a risk signal) and **contradictions** (sources disagree, requiring nuanced interpretation).

### Confirmation Patterns (6 implemented)

| # | Pattern | Sources Combined |
|---|---------|-----------------|
| 1 | Sector concentration reinforced by MF overlap | yfinance allocation + MFapi.in |
| 2 | IT sector + negative forex → margin pressure | yfinance (IT allocation) + RBI DBIE (USD-INR) |
| 3 | Banking sector + high repo rate → rate-sensitive | yfinance (banking allocation) + RBI DBIE (repo rate) |
| 4 | Negative forex trend + negative sentiment alignment | RBI DBIE (forex) + NewsAPI (sentiment) |
| 5 | Multiple holdings with high macro sensitivity | Sector sensitivity model + RBI DBIE |
| 6 | MF overlap stocks also have sentiment shifts | MFapi.in (overlap) + NewsAPI (sentiment) |

### Contradiction Patterns (4 implemented)

| # | Pattern | Sources Combined |
|---|---------|-----------------|
| 1 | Sentiment negative but no concentration stress | Concentration analysis + NewsAPI |
| 2 | Stable macro but deteriorating sentiment → transient? | RBI DBIE + NewsAPI |
| 3 | Sector concentrated but no MF overlap → differentiated | Concentration analysis + MFapi.in |
| 4 | Stock concentration but low macro sensitivity → idiosyncratic risk | Concentration analysis + Sensitivity model |

### Evidence Citations

Every finding includes:
- `confirmed_by_sources` or `contradicted_by_sources`: explicit list of API sources
- `evidence`: specific data values (e.g., `"it_allocation_pct": 35.2`, `"usd_inr_change_30d_pct": -2.0`)
- Net risk direction: `"elevated"` if confirmations > contradictions, else `"mixed"`

## 6. Security

### Token Audience Binding

The `auth0_audience` configuration ensures tokens are issued for this specific API (RFC 8707). The OIDC proxy validates the audience claim.

### API Key Isolation

Upstream API keys (NewsAPI, Alpha Vantage, data.gov.in) are loaded from environment variables and used exclusively server-side. They never appear in MCP tool responses, error messages, or client-visible metadata.

### Audit Logging

Every tool invocation is logged to `audit.log` (NDJSON format) with:
- Timestamp (UTC ISO 8601)
- User identity (`sub` claim from JWT)
- User tier
- Operation name (tool name)
- Outcome (success/error)
- Error detail (if applicable)

### Input Validation

Tool inputs are validated against JSON schemas defined in `TOOL_CONTRACTS`. Invalid inputs return MCP error code `-32602` (Invalid params).

### Disclaimer

All tool responses include a legal disclaimer: *"This output is for informational purposes only and does not constitute financial advice."*
