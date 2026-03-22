# PS2 Must-Show Demo Runbook

## Goal

Demonstrate auth flow, tier-aware discovery, permission boundaries, cross-source output, and subscription alerts.

## Prerequisites

- Server running at `http://localhost:8000`.
- Three Auth0 tokens with tier claim:
  - Free
  - Premium
  - Analyst

## Step 1: Resource metadata and auth boundary

1. Call `GET /.well-known/oauth-protected-resource`.
2. Call `GET /mcp/capabilities` without token.
3. Verify:
  - `401`
  - `WWW-Authenticate` includes `resource_metadata` URL.

## Step 2: Free tier path

1. `POST /mcp/tools/add_to_portfolio` with 3 holdings.
2. `POST /mcp/tools/get_portfolio_summary` succeeds.
3. `POST /mcp/tools/portfolio_risk_report` fails with `403 insufficient_scope`.

## Step 3: Premium tier path

1. `GET /mcp/capabilities` and show richer tool list.
2. Run:
  - `portfolio_health_check`
  - `check_mf_overlap`
  - `detect_sentiment_shift`
3. Attempt `what_if_analysis` and show `403 insufficient_scope`.

## Step 4: Analyst tier path

1. Run `portfolio_risk_report` and show:
  - confirmations
  - contradictions
  - source citations
2. Run `what_if_analysis` with `{ \"rate_change_bps\": -25 }`.

## Step 5: Subscription differentiator

1. `POST /mcp/resources/subscribe` for:
  - `portfolio://{user_id}/alerts`
2. Run `portfolio_health_check` or `portfolio_risk_report`.
3. `GET /mcp/resources/events` and show emitted alert update event.

## Step 6: Reliability proofs

- Trigger high request volume to get `429` with `Retry-After`.
- Show audit log entries in `audit.log`.
- Show cached response speedup for repeated summary/news calls.

