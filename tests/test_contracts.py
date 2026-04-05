"""Tests for contract definitions and tier access rules."""

from app.core.contracts import (
    PROMPT_CONTRACTS,
    RESOURCE_CONTRACTS,
    SCOPES,
    TIER_ANALYST,
    TIER_FREE,
    TIER_PREMIUM,
    TOOL_CONTRACTS,
)


class TestScopes:
    def test_all_expected_scopes_present(self):
        expected = {
            "market:read", "fundamentals:read", "technicals:read",
            "mf:read", "news:read", "filings:read", "filings:deep",
            "macro:read", "macro:historical", "research:generate",
            "watchlist:read", "watchlist:write",
            "portfolio:read", "portfolio:write",
        }
        assert SCOPES == expected

    def test_tool_scopes_are_subset_of_global_scopes(self):
        for name, tc in TOOL_CONTRACTS.items():
            assert tc.required_scopes.issubset(SCOPES), (
                f"Tool '{name}' requires scopes not in global SCOPES: "
                f"{tc.required_scopes - SCOPES}"
            )


class TestToolContracts:
    def test_all_ps2_tools_present(self):
        required = {
            "add_to_portfolio", "remove_from_portfolio", "get_portfolio_summary",
            "portfolio_health_check", "check_concentration_risk", "check_mf_overlap",
            "check_macro_sensitivity", "detect_sentiment_shift",
            "get_stock_quote", "get_price_history", "get_index_data",
            "get_top_gainers_losers", "get_shareholding_pattern",
            "get_company_news", "get_news_sentiment",
            "get_rbi_rates", "get_inflation_data",
            "search_mutual_funds", "get_fund_nav",
            "portfolio_risk_report", "what_if_analysis",
        }
        assert required.issubset(set(TOOL_CONTRACTS.keys()))

    def test_free_tier_tools(self):
        free_tools = {
            "add_to_portfolio", "remove_from_portfolio", "get_portfolio_summary",
            "get_stock_quote", "get_price_history", "get_index_data",
            "get_top_gainers_losers", "get_company_news", "get_news_sentiment",
            "search_mutual_funds", "get_fund_nav",
        }
        for name in free_tools:
            assert TIER_FREE in TOOL_CONTRACTS[name].allowed_tiers, (
                f"Tool '{name}' should be available to free tier"
            )

    def test_premium_only_tools(self):
        premium_tools = {
            "portfolio_health_check", "check_concentration_risk",
            "check_mf_overlap", "check_macro_sensitivity",
            "detect_sentiment_shift",
        }
        for name in premium_tools:
            tc = TOOL_CONTRACTS[name]
            assert TIER_PREMIUM in tc.allowed_tiers, f"'{name}' should allow premium"
            assert TIER_ANALYST in tc.allowed_tiers, f"'{name}' should allow analyst"
            assert TIER_FREE not in tc.allowed_tiers, f"'{name}' should block free"

    def test_analyst_only_tools(self):
        analyst_tools = {"portfolio_risk_report", "what_if_analysis"}
        for name in analyst_tools:
            tc = TOOL_CONTRACTS[name]
            assert tc.allowed_tiers == {TIER_ANALYST}, (
                f"'{name}' should be analyst-only but has {tc.allowed_tiers}"
            )

    def test_cross_source_flag(self):
        assert TOOL_CONTRACTS["portfolio_risk_report"].cross_source is True
        assert TOOL_CONTRACTS["what_if_analysis"].cross_source is True
        assert TOOL_CONTRACTS["get_stock_quote"].cross_source is False

    def test_every_tool_has_input_output_schema(self):
        for name, tc in TOOL_CONTRACTS.items():
            assert "type" in tc.input_schema, f"Tool '{name}' missing input_schema type"
            assert "type" in tc.output_schema, f"Tool '{name}' missing output_schema type"


class TestResourceContracts:
    def test_all_ps2_resources_present(self):
        uris = {rc.uri_template for rc in RESOURCE_CONTRACTS}
        expected = {
            "portfolio://{user_id}/holdings",
            "portfolio://{user_id}/alerts",
            "portfolio://{user_id}/risk_score",
            "market://overview",
            "macro://snapshot",
        }
        assert expected == uris

    def test_subscribable_resources(self):
        subscribable = {
            rc.uri_template for rc in RESOURCE_CONTRACTS if rc.subscribable
        }
        expected = {
            "portfolio://{user_id}/alerts",
            "portfolio://{user_id}/risk_score",
            "market://overview",
            "macro://snapshot",
        }
        assert expected == subscribable

    def test_holdings_available_to_free(self):
        for rc in RESOURCE_CONTRACTS:
            if rc.uri_template == "portfolio://{user_id}/holdings":
                assert TIER_FREE in rc.allowed_tiers


class TestPromptContracts:
    def test_all_ps2_prompts_present(self):
        names = {pc.name for pc in PROMPT_CONTRACTS}
        assert names == {"morning_risk_brief", "rebalance_suggestions", "earnings_exposure"}

    def test_prompts_require_premium(self):
        for pc in PROMPT_CONTRACTS:
            assert TIER_FREE not in pc.allowed_tiers, (
                f"Prompt '{pc.name}' should not be available to free tier"
            )
            assert TIER_PREMIUM in pc.allowed_tiers
            assert TIER_ANALYST in pc.allowed_tiers
