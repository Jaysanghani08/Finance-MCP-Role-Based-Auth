# PS2 MCP Server — API Reference

## Tools

### Market Data

#### `get_stock_quote`
Live/latest quote for an NSE/BSE ticker.

- **Scopes:** `market:read`
- **Tiers:** free, premium, analyst
- **Input:** `{ "ticker": string }`
- **Output:** `{ "data": { "ticker", "ltp", "change_pct", "volume", "timestamp" }, "citations": [...], "disclaimer": "..." }`

#### `get_price_history`
Historical OHLCV for a ticker. Supports pagination.

- **Scopes:** `market:read`
- **Tiers:** free, premium, analyst
- **Input:** `{ "ticker": string, "days?": number, "limit?": number, "cursor?": string }`
- **Output:** `{ "data": { "ticker", "items": [{ "date", "open", "high", "low", "close", "volume" }], "page_info": { "limit", "next_cursor", "total_items" } }, ... }`

#### `get_index_data`
Current Nifty 50 and Sensex values.

- **Scopes:** `market:read`
- **Tiers:** free, premium, analyst
- **Input:** `{}`
- **Output:** `{ "data": { "nifty50": { "value", "change_pct" }, "sensex": { "value", "change_pct" } }, ... }`

#### `get_top_gainers_losers`
Today's top movers.

- **Scopes:** `market:read`
- **Tiers:** free, premium, analyst
- **Input:** `{}`
- **Output:** `{ "data": { "gainers": [...], "losers": [...] }, ... }`

### Portfolio Management

#### `add_to_portfolio`
Add a stock holding with quantity and average buy price.

- **Scopes:** `portfolio:write`
- **Tiers:** free, premium, analyst
- **Input:** `{ "ticker": string, "quantity": number, "avg_buy_price": number, "sector": string }`
- **Output:** `{ "data": { "holdings": [...] }, ... }`

#### `remove_from_portfolio`
Remove a stock holding.

- **Scopes:** `portfolio:write`
- **Tiers:** free, premium, analyst
- **Input:** `{ "ticker": string }`
- **Output:** `{ "data": { "holdings": [...] }, ... }`

#### `get_portfolio_summary`
Current value, P&L, and allocation breakdown by stock and sector.

- **Scopes:** `portfolio:read`, `market:read`
- **Tiers:** free, premium, analyst
- **Input:** `{}`
- **Output:** `{ "data": { "total_value", "total_pnl", "positions": [...], "allocation_by_sector_pct": {...} }, ... }`

### Risk Detection

#### `portfolio_health_check`
Evaluate concentration and sector exposure risk.

- **Scopes:** `portfolio:read`, `market:read`
- **Tiers:** premium, analyst
- **Input:** `{}`
- **Output:** `{ "data": { "health_check": { "stock_concentration_breaches", "sector_concentration_breaches", "top_holdings_pct", "sector_exposure_pct" }, "risk_score": {...} }, ... }`

#### `check_concentration_risk`
Detect single-stock (>20%) and sector (>40%) concentration risk.

- **Scopes:** `portfolio:read`, `market:read`
- **Tiers:** premium, analyst
- **Input:** `{}`
- **Output:** `{ "data": { "stock_concentration_breaches", "sector_concentration_breaches", "top_holdings_pct", "sector_exposure_pct" }, ... }`

#### `check_mf_overlap`
Check overlap between portfolio holdings and popular large-cap MF schemes.

- **Scopes:** `portfolio:read`, `mf:read`
- **Tiers:** premium, analyst
- **Input:** `{}`
- **Output:** `{ "data": { "overlaps": [{ "scheme", "overlap_count", "overlap_tickers" }] }, ... }`

#### `check_macro_sensitivity`
Assess sensitivity of holdings to RBI rates, inflation, and forex moves.

- **Scopes:** `portfolio:read`, `macro:read`
- **Tiers:** premium, analyst
- **Input:** `{}`
- **Output:** `{ "data": { "macro_snapshot": {...}, "holding_exposure": [{ "ticker", "sector", "sensitivity_score" }] }, ... }`

#### `detect_sentiment_shift`
Detect 7-day sentiment shifts versus 30-day baseline for each holding.

- **Scopes:** `portfolio:read`, `news:read`
- **Tiers:** premium, analyst
- **Input:** `{}`
- **Output:** `{ "data": { "shifts": [{ "ticker", "sentiment_7d", "sentiment_30d", "delta", "shift_detected" }] }, ... }`

### Cross-Source Reasoning (Analyst Only)

#### `portfolio_risk_report`
Full cross-source risk report combining market data, macro, MF overlap, and sentiment.

- **Scopes:** `portfolio:read`, `market:read`, `macro:read`, `mf:read`, `news:read`, `research:generate`
- **Tiers:** analyst
- **Input:** `{}`
- **Output:**
```json
{
  "data": {
    "report": {
      "generated_at": "ISO8601",
      "portfolio_summary": {...},
      "concentration_risk": {...},
      "mf_overlap": {...},
      "macro_sensitivity": {...},
      "sentiment_shift": {...},
      "cross_source_analysis": {
        "total_sources_consulted": 5,
        "sources": ["NSE/yfinance", "MFapi.in", "RBI DBIE", "NewsAPI", "Sector model"],
        "confirmations": [{ "finding", "confirmed_by_sources", "evidence" }],
        "contradictions": [{ "finding", "contradicted_by_sources", "evidence" }],
        "signals_summary": { "confirming_signals", "contradicting_signals", "net_risk_direction" }
      }
    },
    "risk_score": { "score", "breakdown": { "concentration", "overlap", "macro", "sentiment" } }
  },
  "citations": [...],
  "disclaimer": "..."
}
```

#### `what_if_analysis`
Scenario analysis: "What happens if RBI changes rates by N bps?"

- **Scopes:** `portfolio:read`, `market:read`, `macro:historical`, `research:generate`
- **Tiers:** analyst
- **Input:** `{ "rate_change_bps": number }`
- **Output:**
```json
{
  "data": {
    "scenario": { "rate_change_bps", "direction", "current_repo_rate", "projected_repo_rate" },
    "portfolio_impact": { "current_total_value", "weighted_impact_pct", "estimated_total_value_change" },
    "holding_impacts": [{ "ticker", "sector", "current_value", "estimated_price_impact_pct", "estimated_value_change", "portfolio_weight_pct" }],
    "analysis": { "beneficiaries", "adversely_affected", "narrative" }
  },
  "citations": [...],
  "disclaimer": "..."
}
```

### Supporting Tools

#### `get_shareholding_pattern`
Promoter/FII/DII/retail holdings over time.

- **Scopes:** `fundamentals:read`
- **Tiers:** premium, analyst
- **Input:** `{ "ticker": string }`

#### `get_company_news`
Latest news articles for a company. Supports pagination.

- **Scopes:** `news:read`
- **Tiers:** free, premium, analyst
- **Input:** `{ "ticker": string, "limit?": number, "cursor?": string, "days?": number }`

#### `get_news_sentiment`
Aggregated sentiment for a stock over a time window.

- **Scopes:** `news:read`
- **Tiers:** free, premium, analyst
- **Input:** `{ "ticker": string, "window_days?": number }`

#### `get_rbi_rates`
Current RBI rates (repo, reverse repo, CRR, SLR).

- **Scopes:** `macro:read`
- **Tiers:** premium, analyst
- **Input:** `{}`

#### `get_inflation_data`
CPI, WPI, GDP growth, forex reserves, USD-INR.

- **Scopes:** `macro:read`
- **Tiers:** premium, analyst
- **Input:** `{}`

#### `search_mutual_funds`
Search mutual fund schemes by keyword.

- **Scopes:** `mf:read`
- **Tiers:** free, premium, analyst
- **Input:** `{ "query": string }`

#### `get_fund_nav`
Latest NAV for a mutual fund scheme.

- **Scopes:** `mf:read`
- **Tiers:** free, premium, analyst
- **Input:** `{ "scheme_code": string }`

### Subscription Helper Tools

#### `ps2_resource_subscribe`
Subscribe to change notifications for a subscribable resource.
- **Input:** `{ "uri": string }`

#### `ps2_resource_unsubscribe`
Unsubscribe from a resource.
- **Input:** `{ "uri": string }`

#### `ps2_resource_pull_events`
Pull pending subscription events for the authenticated user.
- **Input:** `{}`

---

## Resources

| URI Template | Description | Subscribable | Tiers |
|-------------|-------------|-------------|-------|
| `portfolio://{user_id}/holdings` | User's persisted portfolio holdings | No | all |
| `portfolio://{user_id}/alerts` | Active risk alerts for the portfolio | Yes | premium, analyst |
| `portfolio://{user_id}/risk_score` | Aggregate portfolio risk score | Yes | premium, analyst |
| `market://overview` | Market summary (Nifty 50, Sensex) | Yes | all |
| `macro://snapshot` | Latest macro indicators | Yes | premium, analyst |

---

## Prompts

#### `morning_risk_brief`
Daily risk brief: portfolio value + sentiment shifts + macro changes.

- **Tiers:** premium, analyst
- **Arguments:** none
- **Composes:** `get_portfolio_summary` + `detect_sentiment_shift` + `macro://snapshot`

#### `rebalance_suggestions`
Data-driven suggestions to reduce concentration and sector tilt.

- **Tiers:** premium, analyst
- **Arguments:** none
- **Composes:** `portfolio_health_check` + `check_mf_overlap`

#### `earnings_exposure`
Which holdings have upcoming earnings and what's the risk level.

- **Tiers:** premium, analyst
- **Arguments:** none

---

## HTTP Endpoints (Non-MCP)

#### `GET /.well-known/oauth-protected-resource`
RFC 9728 Protected Resource Metadata. Returns authorization server URL and supported scopes.

#### `GET /health`
Health check showing upstream API status and remaining quotas.

Response:
```json
{
  "status": "ok|degraded",
  "upstream_apis": {
    "yahoo_finance": { "status": "ok", "http_code": 200 },
    "mfapi": { "status": "ok", "http_code": 200 },
    "rbi_proxy": { "status": "ok", "http_code": 200 },
    "newsapi": { "status": "ok|not_configured", "http_code": 200 }
  },
  "upstream_quotas": {
    "newsapi_daily": { "limit": 100, "used": 5, "remaining": 95, "window": "1 day" }
  },
  "server": { "name": "ps2-mcp-server", "version": "0.1.0" }
}
```

---

## Scope Requirements Summary

| Scope | Tools |
|-------|-------|
| `market:read` | get_stock_quote, get_price_history, get_index_data, get_top_gainers_losers |
| `fundamentals:read` | get_shareholding_pattern |
| `mf:read` | search_mutual_funds, get_fund_nav, check_mf_overlap |
| `news:read` | get_company_news, get_news_sentiment, detect_sentiment_shift |
| `macro:read` | get_rbi_rates, get_inflation_data, check_macro_sensitivity |
| `macro:historical` | what_if_analysis |
| `research:generate` | portfolio_risk_report, what_if_analysis |
| `portfolio:read` | get_portfolio_summary, portfolio_health_check, check_concentration_risk, all risk tools |
| `portfolio:write` | add_to_portfolio, remove_from_portfolio |

## Error Codes

| MCP Code | Meaning | HTTP Equivalent |
|----------|---------|----------------|
| `-32003` | `insufficient_scope` — tier/scope not permitted | 403 |
| `-32029` | `rate_limited` — user exceeded hourly quota (includes `retry_after`) | 429 |
| `-32050` | `upstream_failure` — upstream API failed, no cache fallback | 502 |
| `-32602` | `Invalid params` — input validation failed | 400 |
