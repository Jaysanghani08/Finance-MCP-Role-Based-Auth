# API Reference

All responses are structured JSON with:

- `data` (object)
- `citations` (array of source references)
- `disclaimer` (non-advice statement)

## Authentication

- Bearer token required for all `/mcp/*` endpoints.
- Discovery endpoint: `GET /.well-known/oauth-protected-resource`

## Capability and Contracts

- `GET /mcp/capabilities`
  - Returns tier/scope-filtered tools/resources/prompts.
- `GET /mcp/contracts`
  - Returns operation contracts (schemas, scopes, tiers).

## Tool Invocation

- `POST /mcp/tools/{tool_name}`
- Body:

```json
{
  "arguments": {}
}
```

### Implemented tools

- Market/shared:
  - `get_stock_quote`
  - `get_price_history`
  - `get_index_data`
  - `get_top_gainers_losers`
  - `get_shareholding_pattern`
  - `get_company_news`
  - `get_news_sentiment`
  - `get_rbi_rates`
  - `get_inflation_data`
  - `search_mutual_funds`
  - `get_fund_nav`
- Portfolio/risk:
  - `add_to_portfolio`
  - `remove_from_portfolio`
  - `get_portfolio_summary`
  - `portfolio_health_check`
  - `check_concentration_risk`
  - `check_mf_overlap`
  - `check_macro_sensitivity`
  - `detect_sentiment_shift`
  - `portfolio_risk_report` (cross-source, analyst)
  - `what_if_analysis` (cross-source, analyst)

## Resource Operations

- `POST /mcp/resources/read`
  - Body: `{ "uri": "portfolio://<user_id>/holdings" }`
- `POST /mcp/resources/subscribe`
  - Body: `{ "uri": "<resource_uri>" }`
- `POST /mcp/resources/unsubscribe`
- `GET /mcp/resources/events`

### Resource URIs

- `portfolio://{user_id}/holdings`
- `portfolio://{user_id}/alerts`
- `portfolio://{user_id}/risk_score`
- `market://overview`
- `macro://snapshot`

## Prompt Invocation

- `POST /mcp/prompts/invoke`
- Body:

```json
{
  "name": "morning_risk_brief",
  "arguments": {}
}
```

### Implemented prompts

- `morning_risk_brief`
- `rebalance_suggestions`
- `earnings_exposure`

## Error Semantics

- `401` unauthenticated + `WWW-Authenticate` with resource metadata discovery.
- `403` authenticated but unauthorized scope/tier (`insufficient_scope`).
- `429` rate limited + `Retry-After`.
- `502` upstream adapter failure when no graceful fallback is available.
