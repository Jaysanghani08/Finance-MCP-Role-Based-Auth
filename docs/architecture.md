# PS2 MCP Server — Architecture

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        MCP Client (Cursor / Claude Desktop)         │
│   ┌────────────┐  OAuth 2.1 + PKCE   ┌──────────────────────────┐  │
│   │  User UI   │ ◄──────────────────► │  Browser (Auth0 Login)   │  │
│   └─────┬──────┘                      └──────────────────────────┘  │
│         │ Bearer Token                                              │
└─────────┼───────────────────────────────────────────────────────────┘
          │ Streamable HTTP (/mcp)
          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     PS2 MCP Server (FastMCP 3.x)                    │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    HTTP / ASGI Layer                          │   │
│  │  /.well-known/oauth-protected-resource  (RFC 9728)           │   │
│  │  /health                                (Health Check)       │   │
│  │  /mcp                                   (MCP Streamable HTTP)│   │
│  │  WWW-Authenticate middleware            (401 discovery)      │   │
│  └──────────────┬───────────────────────────────────────────────┘   │
│                 │                                                    │
│  ┌──────────────▼───────────────────────────────────────────────┐   │
│  │                  Auth0 OIDC Proxy (FastMCP)                  │   │
│  │  • OIDC discovery metadata                                   │   │
│  │  • Dynamic client registration                               │   │
│  │  • Authorization code + PKCE exchange                        │   │
│  │  • Token validation (JWT signature, expiry, audience)        │   │
│  └──────────────┬───────────────────────────────────────────────┘   │
│                 │ AuthContext (sub, tier, scopes)                    │
│  ┌──────────────▼───────────────────────────────────────────────┐   │
│  │               Contract-Based Access Control                  │   │
│  │  • Tier gate (free / premium / analyst) → tool visibility    │   │
│  │  • Scope enforcement at execution time                       │   │
│  │  • Rate limiting (30 / 150 / 500 calls/hour)                │   │
│  └──────────────┬───────────────────────────────────────────────┘   │
│                 │                                                    │
│  ┌──────────────▼───────────────────────────────────────────────┐   │
│  │                     MCP Service Layer                        │   │
│  │                                                              │   │
│  │  Tools (21)           Resources (5)       Prompts (3)        │   │
│  │  ├─ Portfolio mgmt    ├─ holdings         ├─ morning_risk    │   │
│  │  ├─ Risk detection    ├─ alerts           ├─ rebalance       │   │
│  │  ├─ Market data       ├─ risk_score       └─ earnings_exp    │   │
│  │  ├─ Supporting        ├─ market overview                     │   │
│  │  └─ Cross-source      └─ macro snapshot                      │   │
│  │                                                              │   │
│  │  Subscription Service   Audit Logger   Upstream Quota Mgr    │   │
│  └──────────────┬───────────────────────────────────────────────┘   │
│                 │                                                    │
│  ┌──────────────▼───────────────────────────────────────────────┐   │
│  │                     Risk Engine                              │   │
│  │  portfolio_summary · concentration_risk · mf_overlap         │   │
│  │  macro_sensitivity · sentiment_shift · risk_score            │   │
│  │  cross_source_report (6 confirmation + 4 contradiction       │   │
│  │    patterns across 5 data sources)                           │   │
│  │  what_if_analysis (scenario modeling)                        │   │
│  └──────────────┬───────────────────────────────────────────────┘   │
│                 │                                                    │
│  ┌──────────────▼───────────────────────────────────────────────┐   │
│  │                  Data Adapters (Upstream APIs)                │   │
│  │                                                              │   │
│  │  MarketDataAdapter   → Yahoo Finance (yfinance .NS)          │   │
│  │  NewsDataAdapter     → NewsAPI.org (/v2/everything)          │   │
│  │  MacroDataAdapter    → RBI DBIE (via allorigins proxy)       │   │
│  │  MutualFundAdapter   → MFapi.in (/mf/{scheme_code})         │   │
│  │                                                              │   │
│  │  Every adapter has deterministic fallback on upstream failure │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Persistence Layer                          │   │
│  │  TTLCache (in-memory)  │  JsonStore (data_store.json)        │   │
│  │  • quotes: 60s TTL     │  • portfolios per user              │   │
│  │  • news: 1800s TTL     │  • alerts per user                  │   │
│  │  • macro: 1800s TTL    │  • risk scores per user             │   │
│  │  • summaries: 60s TTL  │                                     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  audit.log (NDJSON) — every tool invocation with identity + tier    │
└──────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Auth0 (External IdP)                              │
│  • OAuth 2.1 Authorization Server                                   │
│  • PKCE support for public clients                                  │
│  • Custom JWT claim: https://ps2.example.com/tier                   │
│  • RBAC permissions → OAuth scopes                                  │
└──────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **FastMCP OIDC Proxy** | Handles OAuth 2.1 discovery, PKCE flow, token exchange with Auth0 |
| **Contract System** | Declares every tool/resource/prompt with required scopes and allowed tiers |
| **Access Control** | Enforces tier + scope checks before every operation |
| **Rate Limiter** | Sliding-window per-user hourly limits (30/150/500) |
| **MCPService** | Orchestrates tool execution, caching, audit, subscriptions |
| **RiskEngine** | Cross-source analysis combining data from 4+ upstream APIs |
| **Data Adapters** | Upstream API clients with graceful fallback on failure |
| **TTLCache** | In-memory cache with per-data-type TTLs |
| **JsonStore** | Persistent user data (portfolios, alerts, risk scores) |
| **AuditLogger** | Append-only NDJSON log of every tool invocation |
| **SubscriptionService** | In-memory pub/sub for resource change events |
| **UpstreamQuotaManager** | Tracks upstream API usage to avoid burning free-tier quotas |

## Auth Flow

```
Client                    MCP Server (OIDC Proxy)          Auth0
  │                              │                           │
  │─── GET /mcp ────────────────►│                           │
  │◄── 401 + WWW-Authenticate ──│                           │
  │    (resource_metadata URL)   │                           │
  │                              │                           │
  │─── GET /.well-known/... ────►│                           │
  │◄── Protected Resource Meta ──│                           │
  │                              │                           │
  │─── OAuth /authorize ────────►│──── /authorize ──────────►│
  │◄── Auth Code + PKCE ────────│◄── Auth Code ─────────────│
  │                              │                           │
  │─── Exchange code ───────────►│──── /oauth/token ────────►│
  │◄── Access Token (JWT) ──────│◄── Token ─────────────────│
  │                              │                           │
  │─── MCP Request + Bearer ────►│                           │
  │    (tools/resources/prompts) │                           │
  │◄── MCP Response ────────────│                           │
```

## Tier → Scope → Permission Mapping

See `docs/scope_tier_matrix.md` for the complete mapping.
