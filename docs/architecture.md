# PS2 MCP Server — Architecture

## High-Level Architecture

```mermaid
flowchart TD
    Client["🖥 MCP Client\n(Cursor / Claude Desktop)"]

    Client -->|"Streamable HTTP + Bearer Token"| HTTP

    subgraph PS2["PS2 MCP Server (FastMCP 3.x)"]
        HTTP["/mcp · /health · /.well-known"]
        OIDC["Auth0 OIDC Proxy\nPKCE · JWT Validation"]
        ACL["Access Control\nTier Gate · Scope Check · Rate Limit"]

        HTTP --> OIDC --> ACL

        ACL --> Tools["21 Tools"]
        ACL --> Res["5 Resources"]
        ACL --> Prompts["3 Prompts"]

        Tools --> RiskEngine["Risk Engine\ncross_source_report\nwhat_if_analysis"]
        Tools --> Svc["Subscriptions · Audit · Quotas"]

        RiskEngine --> A1["MarketData\nYahoo Finance"]
        RiskEngine --> A2["NewsData\nNewsAPI.org"]
        RiskEngine --> A3["MacroData\nRBI DBIE"]
        RiskEngine --> A4["MutualFund\nMFapi.in"]

        Tools --> Cache["TTLCache\n60s–30min"]
        Tools --> Store["JsonStore\nPortfolios · Alerts"]
        Svc --> AuditLog["audit.log\nNDJSON"]
    end

    OIDC <-->|"Token Exchange"| Auth0["Auth0\nOAuth 2.1 IdP"]
```

### Server Layers (detailed)

```mermaid
flowchart LR
    subgraph Layer1["HTTP Layer"]
        E1["/mcp — MCP transport"]
        E2["/health — status + quotas"]
        E3["/.well-known — RFC 9728"]
        E4["WWW-Authenticate middleware"]
    end

    subgraph Layer2["Auth Layer"]
        O1["OIDC discovery"]
        O2["PKCE code exchange"]
        O3["JWT signature + expiry + aud"]
    end

    subgraph Layer3["Access Control"]
        T1["Tier: free / premium / analyst"]
        T2["Scope enforcement"]
        T3["Rate limit: 30 / 150 / 500 per hr"]
    end

    subgraph Layer4["Service Layer"]
        S1["21 Tools"]
        S2["5 Resources"]
        S3["3 Prompts"]
    end

    subgraph Layer5["Risk Engine"]
        R1["portfolio_summary"]
        R2["concentration_risk"]
        R3["mf_overlap"]
        R4["macro_sensitivity"]
        R5["sentiment_shift"]
        R6["cross_source_report"]
        R7["what_if_analysis"]
    end

    subgraph Layer6["Persistence"]
        P1["TTLCache — quotes 60s, news 30min"]
        P2["JsonStore — portfolios, alerts, scores"]
        P3["audit.log — every invocation"]
    end

    Layer1 --> Layer2 --> Layer3 --> Layer4 --> Layer5 --> Layer6
```

## Auth Flow

```mermaid
sequenceDiagram
    participant C as MCP Client
    participant S as MCP Server<br>(OIDC Proxy)
    participant A as Auth0

    C->>S: GET /mcp (no token)
    S-->>C: 401 + WWW-Authenticate<br>resource_metadata URL

    C->>S: GET /.well-known/oauth-protected-resource
    S-->>C: Protected Resource Metadata<br>(auth server, scopes)

    C->>S: OAuth /authorize + PKCE challenge
    S->>A: Forward /authorize
    A-->>S: Authorization code
    S-->>C: Authorization code

    C->>S: Exchange code + PKCE verifier
    S->>A: POST /oauth/token
    A-->>S: Access Token (JWT)
    S-->>C: Access Token (JWT)

    Note over C,S: Authenticated session established

    C->>S: MCP Request + Bearer token<br>(tools / resources / prompts)
    S->>S: Validate JWT · Check tier · Enforce scopes · Rate limit
    S-->>C: MCP Response (structured JSON + citations)
```

## Tier Access Control

```mermaid
graph LR
    subgraph Tiers
        Free["Free Tier<br>30 calls/hr"]
        Premium["Premium Tier<br>150 calls/hr"]
        Analyst["Analyst Tier<br>500 calls/hr"]
    end

    subgraph Free_Tools["Free Tier Tools"]
        F1["add/remove_portfolio<br>get_portfolio_summary"]
        F2["get_stock_quote<br>get_price_history"]
        F3["get_index_data<br>get_top_gainers_losers"]
        F4["get_company_news<br>get_news_sentiment"]
        F5["search_mutual_funds<br>get_fund_nav"]
    end

    subgraph Premium_Tools["+ Premium Tier Tools"]
        P1["portfolio_health_check<br>check_concentration_risk"]
        P2["check_mf_overlap<br>check_macro_sensitivity"]
        P3["detect_sentiment_shift"]
        P4["get_shareholding_pattern<br>get_rbi_rates · get_inflation_data"]
        P5["Prompts: morning_risk_brief<br>rebalance_suggestions<br>earnings_exposure"]
        P6["Resource subscriptions:<br>alerts · risk_score"]
    end

    subgraph Analyst_Tools["+ Analyst Tier Tools"]
        A1["portfolio_risk_report<br>(cross-source)"]
        A2["what_if_analysis<br>(cross-source)"]
    end

    Free --> Free_Tools
    Premium --> Free_Tools
    Premium --> Premium_Tools
    Analyst --> Free_Tools
    Analyst --> Premium_Tools
    Analyst --> Analyst_Tools
```

## Cross-Source Data Flow

```mermaid
flowchart LR
    subgraph Sources["Data Sources"]
        Y["Yahoo Finance"]
        N["NewsAPI.org"]
        R["RBI DBIE"]
        M["MFapi.in"]
        S["Sector Model"]
    end

    subgraph Analyses["Risk Engine Analyses"]
        PS["Portfolio\nSummary"]
        CR["Concentration\nRisk"]
        MO["MF\nOverlap"]
        MS["Macro\nSensitivity"]
        SS["Sentiment\nShift"]
    end

    Y --> PS & CR
    M --> MO
    R --> MS
    N --> SS
    S --> MS

    PS & CR & MO & MS & SS --> XR

    XR["Cross-Reference\nEngine"]

    XR --> C["✅ Confirmations (6)"]
    XR --> D["⚠️ Contradictions (4)"]

    C & D --> Report["Risk Report\n+ citations\n+ risk direction"]
```

### Confirmation & Contradiction Patterns

```mermaid
flowchart TD
    subgraph confirm["✅ 6 Confirmation Patterns"]
        C1["Sector concentration\n+ MF overlap"]
        C2["IT exposure\n+ negative forex"]
        C3["Banking exposure\n+ high repo rate"]
        C4["Negative forex\n+ negative sentiment"]
        C5["Multiple holdings\nhigh macro sensitivity"]
        C6["MF overlap stocks\n+ sentiment shifts"]
    end

    subgraph contra["⚠️ 4 Contradiction Patterns"]
        D1["Negative sentiment\nbut no concentration"]
        D2["Stable macro\nbut bad sentiment"]
        D3["Sector concentrated\nbut no MF overlap"]
        D4["Stock concentrated\nbut low macro sensitivity"]
    end

    confirm --> V["Net Risk Direction"]
    contra --> V
    V -->|"elevated / mixed"| OUT["Structured Report\nwith source citations"]
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

## Tier → Scope → Permission Mapping

See `docs/scope_tier_matrix.md` for the complete mapping.
