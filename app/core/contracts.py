from __future__ import annotations

from dataclasses import dataclass
from typing import Any


TIER_FREE = "free"
TIER_PREMIUM = "premium"
TIER_ANALYST = "analyst"
TIERS = (TIER_FREE, TIER_PREMIUM, TIER_ANALYST)

SCOPES = {
    "market:read",
    "fundamentals:read",
    "technicals:read",
    "mf:read",
    "news:read",
    "filings:read",
    "filings:deep",
    "macro:read",
    "macro:historical",
    "research:generate",
    "watchlist:read",
    "watchlist:write",
    "portfolio:read",
    "portfolio:write",
}


@dataclass(frozen=True)
class MCPToolContract:
    name: str
    description: str
    required_scopes: set[str]
    allowed_tiers: set[str]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    cross_source: bool = False


@dataclass(frozen=True)
class MCPResourceContract:
    uri_template: str
    description: str
    required_scopes: set[str]
    allowed_tiers: set[str]
    output_schema: dict[str, Any]
    subscribable: bool = False


@dataclass(frozen=True)
class MCPPromptContract:
    name: str
    description: str
    required_scopes: set[str]
    allowed_tiers: set[str]
    arguments_schema: dict[str, Any]


def _source_citation_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "reference": {"type": "string"},
                "as_of": {"type": "string"},
            },
            "required": ["source", "reference"],
        },
    }


COMMON_TOOL_OUTPUT = {
    "type": "object",
    "properties": {
        "data": {"type": "object"},
        "citations": _source_citation_schema(),
        "disclaimer": {"type": "string"},
    },
    "required": ["data", "citations", "disclaimer"],
}


TOOL_CONTRACTS: dict[str, MCPToolContract] = {
    "get_stock_quote": MCPToolContract(
        name="get_stock_quote",
        description="Live/latest quote for NSE/BSE ticker.",
        required_scopes={"market:read"},
        allowed_tiers={TIER_FREE, TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "get_price_history": MCPToolContract(
        name="get_price_history",
        description="Historical OHLCV for a ticker over date range.",
        required_scopes={"market:read"},
        allowed_tiers={TIER_FREE, TIER_PREMIUM, TIER_ANALYST},
        input_schema={
            "type": "object",
            "properties": {"ticker": {"type": "string"}, "days": {"type": "number"}},
            "required": ["ticker"],
        },
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "get_index_data": MCPToolContract(
        name="get_index_data",
        description="Current index values and composition summary.",
        required_scopes={"market:read"},
        allowed_tiers={TIER_FREE, TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "get_top_gainers_losers": MCPToolContract(
        name="get_top_gainers_losers",
        description="Top gainers and losers for the day.",
        required_scopes={"market:read"},
        allowed_tiers={TIER_FREE, TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "get_shareholding_pattern": MCPToolContract(
        name="get_shareholding_pattern",
        description="Promoter/FII/DII/retail holdings over time.",
        required_scopes={"fundamentals:read"},
        allowed_tiers={TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "get_company_news": MCPToolContract(
        name="get_company_news",
        description="Latest company news for a stock.",
        required_scopes={"news:read"},
        allowed_tiers={TIER_FREE, TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "get_news_sentiment": MCPToolContract(
        name="get_news_sentiment",
        description="Aggregated sentiment for a stock over a time window.",
        required_scopes={"news:read"},
        allowed_tiers={TIER_FREE, TIER_PREMIUM, TIER_ANALYST},
        input_schema={
            "type": "object",
            "properties": {"ticker": {"type": "string"}, "window_days": {"type": "number"}},
            "required": ["ticker"],
        },
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "get_rbi_rates": MCPToolContract(
        name="get_rbi_rates",
        description="Current RBI rates snapshot.",
        required_scopes={"macro:read"},
        allowed_tiers={TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "get_inflation_data": MCPToolContract(
        name="get_inflation_data",
        description="CPI/WPI inflation snapshot.",
        required_scopes={"macro:read"},
        allowed_tiers={TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "search_mutual_funds": MCPToolContract(
        name="search_mutual_funds",
        description="Search mutual fund schemes by keyword.",
        required_scopes={"mf:read"},
        allowed_tiers={TIER_FREE, TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "get_fund_nav": MCPToolContract(
        name="get_fund_nav",
        description="Latest NAV for a mutual fund scheme.",
        required_scopes={"mf:read"},
        allowed_tiers={TIER_FREE, TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {"scheme_code": {"type": "string"}}, "required": ["scheme_code"]},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "add_to_portfolio": MCPToolContract(
        name="add_to_portfolio",
        description="Add a stock holding with quantity and average buy price.",
        required_scopes={"portfolio:write"},
        allowed_tiers={TIER_FREE, TIER_PREMIUM, TIER_ANALYST},
        input_schema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "quantity": {"type": "number"},
                "avg_buy_price": {"type": "number"},
                "sector": {"type": "string"},
            },
            "required": ["ticker", "quantity", "avg_buy_price", "sector"],
        },
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "remove_from_portfolio": MCPToolContract(
        name="remove_from_portfolio",
        description="Remove a stock holding.",
        required_scopes={"portfolio:write"},
        allowed_tiers={TIER_FREE, TIER_PREMIUM, TIER_ANALYST},
        input_schema={
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "get_portfolio_summary": MCPToolContract(
        name="get_portfolio_summary",
        description="Fetch current value, P&L, and allocation by stock and sector.",
        required_scopes={"portfolio:read", "market:read"},
        allowed_tiers={TIER_FREE, TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "portfolio_health_check": MCPToolContract(
        name="portfolio_health_check",
        description="Evaluate concentration and sector exposure risk.",
        required_scopes={"portfolio:read", "market:read"},
        allowed_tiers={TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "check_concentration_risk": MCPToolContract(
        name="check_concentration_risk",
        description="Detect single-stock and sector concentration risk.",
        required_scopes={"portfolio:read", "market:read"},
        allowed_tiers={TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "check_mf_overlap": MCPToolContract(
        name="check_mf_overlap",
        description="Check overlap between portfolio holdings and popular mutual funds.",
        required_scopes={"portfolio:read", "mf:read"},
        allowed_tiers={TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "check_macro_sensitivity": MCPToolContract(
        name="check_macro_sensitivity",
        description="Assess sensitivity of holdings to RBI rates, inflation and forex.",
        required_scopes={"portfolio:read", "macro:read"},
        allowed_tiers={TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "detect_sentiment_shift": MCPToolContract(
        name="detect_sentiment_shift",
        description="Detect 7-day sentiment shifts versus 30-day baseline for holdings.",
        required_scopes={"portfolio:read", "news:read"},
        allowed_tiers={TIER_PREMIUM, TIER_ANALYST},
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=COMMON_TOOL_OUTPUT,
    ),
    "portfolio_risk_report": MCPToolContract(
        name="portfolio_risk_report",
        description="Cross-source portfolio risk report with confirmations and contradictions.",
        required_scopes={"portfolio:read", "market:read", "macro:read", "mf:read", "news:read", "research:generate"},
        allowed_tiers={TIER_ANALYST},
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=COMMON_TOOL_OUTPUT,
        cross_source=True,
    ),
    "what_if_analysis": MCPToolContract(
        name="what_if_analysis",
        description="Cross-source scenario analysis for RBI rate changes.",
        required_scopes={"portfolio:read", "market:read", "macro:historical", "research:generate"},
        allowed_tiers={TIER_ANALYST},
        input_schema={
            "type": "object",
            "properties": {"rate_change_bps": {"type": "number"}},
            "required": ["rate_change_bps"],
        },
        output_schema=COMMON_TOOL_OUTPUT,
        cross_source=True,
    ),
}


RESOURCE_CONTRACTS: list[MCPResourceContract] = [
    MCPResourceContract(
        uri_template="portfolio://{user_id}/holdings",
        description="Persisted user holdings.",
        required_scopes={"portfolio:read"},
        allowed_tiers={TIER_FREE, TIER_PREMIUM, TIER_ANALYST},
        output_schema={"type": "array"},
        subscribable=False,
    ),
    MCPResourceContract(
        uri_template="portfolio://{user_id}/alerts",
        description="Active portfolio alerts.",
        required_scopes={"portfolio:read"},
        allowed_tiers={TIER_PREMIUM, TIER_ANALYST},
        output_schema={"type": "array"},
        subscribable=True,
    ),
    MCPResourceContract(
        uri_template="portfolio://{user_id}/risk_score",
        description="Current aggregate portfolio risk score.",
        required_scopes={"portfolio:read"},
        allowed_tiers={TIER_PREMIUM, TIER_ANALYST},
        output_schema={"type": "object"},
        subscribable=True,
    ),
    MCPResourceContract(
        uri_template="market://overview",
        description="Market summary for tracked holdings.",
        required_scopes={"market:read"},
        allowed_tiers={TIER_FREE, TIER_PREMIUM, TIER_ANALYST},
        output_schema={"type": "object"},
        subscribable=True,
    ),
    MCPResourceContract(
        uri_template="macro://snapshot",
        description="Latest macro indicators snapshot.",
        required_scopes={"macro:read"},
        allowed_tiers={TIER_PREMIUM, TIER_ANALYST},
        output_schema={"type": "object"},
        subscribable=True,
    ),
]


PROMPT_CONTRACTS: list[MCPPromptContract] = [
    MCPPromptContract(
        name="morning_risk_brief",
        description="Daily risk brief for user's portfolio.",
        required_scopes={"portfolio:read", "news:read", "macro:read"},
        allowed_tiers={TIER_PREMIUM, TIER_ANALYST},
        arguments_schema={"type": "object", "properties": {}, "required": []},
    ),
    MCPPromptContract(
        name="rebalance_suggestions",
        description="Suggestions to reduce concentration and sector tilt.",
        required_scopes={"portfolio:read"},
        allowed_tiers={TIER_PREMIUM, TIER_ANALYST},
        arguments_schema={"type": "object", "properties": {}, "required": []},
    ),
    MCPPromptContract(
        name="earnings_exposure",
        description="Portfolio exposure to upcoming earnings.",
        required_scopes={"portfolio:read", "news:read"},
        allowed_tiers={TIER_PREMIUM, TIER_ANALYST},
        arguments_schema={"type": "object", "properties": {}, "required": []},
    ),
]

