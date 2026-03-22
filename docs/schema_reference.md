# Schema and Scope Reference

Canonical source of truth is `app/core/contracts.py`.

## Tool input requirements

- `get_stock_quote`: `{ ticker: string }`
- `get_price_history`: `{ ticker: string, days?: number }`
- `get_index_data`: `{}`
- `get_top_gainers_losers`: `{}`
- `get_shareholding_pattern`: `{ ticker: string }`
- `get_company_news`: `{ ticker: string }`
- `get_news_sentiment`: `{ ticker: string, window_days?: number }`
- `get_rbi_rates`: `{}`
- `get_inflation_data`: `{}`
- `search_mutual_funds`: `{ query: string }`
- `get_fund_nav`: `{ scheme_code: string }`
- `add_to_portfolio`: `{ ticker: string, quantity: number, avg_buy_price: number, sector: string }`
- `remove_from_portfolio`: `{ ticker: string }`
- `get_portfolio_summary`: `{}`
- `portfolio_health_check`: `{}`
- `check_concentration_risk`: `{}`
- `check_mf_overlap`: `{}`
- `check_macro_sensitivity`: `{}`
- `detect_sentiment_shift`: `{}`
- `portfolio_risk_report`: `{}`
- `what_if_analysis`: `{ rate_change_bps: number }`

## Common output schema

All tools/resources/prompts produce:

- `data` (object)
- `citations` (array of `{ source, reference, as_of? }`)
- `disclaimer` (string)

## Scope requirements

See full matrix in `docs/scope_tier_matrix.md`.

## Resource URIs

- `portfolio://{user_id}/holdings`
- `portfolio://{user_id}/alerts`
- `portfolio://{user_id}/risk_score`
- `market://overview`
- `macro://snapshot`

## Prompts

- `morning_risk_brief`
- `rebalance_suggestions`
- `earnings_exposure`
