# PS2 Scope and Tier Matrix

This matrix is implementation-aligned with the PS2 brief.

## Tools


| Tool                       | Scopes                                                                                     | Free | Premium | Analyst |
| -------------------------- | ------------------------------------------------------------------------------------------ | ---- | ------- | ------- |
| `get_stock_quote`          | `market:read`                                                                              | Yes  | Yes     | Yes     |
| `get_price_history`        | `market:read`                                                                              | Yes  | Yes     | Yes     |
| `get_index_data`           | `market:read`                                                                              | Yes  | Yes     | Yes     |
| `get_top_gainers_losers`   | `market:read`                                                                              | Yes  | Yes     | Yes     |
| `get_shareholding_pattern` | `fundamentals:read`                                                                        | No   | Yes     | Yes     |
| `get_company_news`         | `news:read`                                                                                | Yes  | Yes     | Yes     |
| `get_news_sentiment`       | `news:read`                                                                                | Yes  | Yes     | Yes     |
| `get_rbi_rates`            | `macro:read`                                                                               | No   | Yes     | Yes     |
| `get_inflation_data`       | `macro:read`                                                                               | No   | Yes     | Yes     |
| `search_mutual_funds`      | `mf:read`                                                                                  | Yes  | Yes     | Yes     |
| `get_fund_nav`             | `mf:read`                                                                                  | Yes  | Yes     | Yes     |
| `add_to_portfolio`         | `portfolio:write`                                                                          | Yes  | Yes     | Yes     |
| `remove_from_portfolio`    | `portfolio:write`                                                                          | Yes  | Yes     | Yes     |
| `get_portfolio_summary`    | `portfolio:read`, `market:read`                                                            | Yes  | Yes     | Yes     |
| `portfolio_health_check`   | `portfolio:read`, `market:read`                                                            | No   | Yes     | Yes     |
| `check_concentration_risk` | `portfolio:read`, `market:read`                                                            | No   | Yes     | Yes     |
| `check_mf_overlap`         | `portfolio:read`, `mf:read`                                                                | No   | Yes     | Yes     |
| `check_macro_sensitivity`  | `portfolio:read`, `macro:read`                                                             | No   | Yes     | Yes     |
| `detect_sentiment_shift`   | `portfolio:read`, `news:read`                                                              | No   | Yes     | Yes     |
| `portfolio_risk_report`    | `portfolio:read`, `market:read`, `macro:read`, `mf:read`, `news:read`, `research:generate` | No   | No      | Yes     |
| `what_if_analysis`         | `portfolio:read`, `market:read`, `macro:historical`, `research:generate`                   | No   | No      | Yes     |


## Resources


| Resource                           | Scope            | Free | Premium | Analyst | Subscribable |
| ---------------------------------- | ---------------- | ---- | ------- | ------- | ------------ |
| `portfolio://{user_id}/holdings`   | `portfolio:read` | Yes  | Yes     | Yes     | No           |
| `portfolio://{user_id}/alerts`     | `portfolio:read` | No   | Yes     | Yes     | Yes          |
| `portfolio://{user_id}/risk_score` | `portfolio:read` | No   | Yes     | Yes     | Yes          |
| `market://overview`                | `market:read`    | Yes  | Yes     | Yes     | Yes          |
| `macro://snapshot`                 | `macro:read`     | No   | Yes     | Yes     | Yes          |


## Prompts


| Prompt                  | Scope                                       | Free | Premium | Analyst |
| ----------------------- | ------------------------------------------- | ---- | ------- | ------- |
| `morning_risk_brief`    | `portfolio:read`, `news:read`, `macro:read` | No   | Yes     | Yes     |
| `rebalance_suggestions` | `portfolio:read`                            | No   | Yes     | Yes     |
| `earnings_exposure`     | `portfolio:read`, `news:read`               | No   | Yes     | Yes     |


