"""Tests for the risk engine analysis logic."""

import pytest

from app.models.domain import Holding
from app.services.risk_engine import RiskEngine
from app.adapters.market_data import MarketDataAdapter
from app.adapters.news_data import NewsDataAdapter
from app.adapters.macro_data import MacroDataAdapter
from app.adapters.mf_data import MutualFundAdapter


@pytest.fixture
def engine():
    return RiskEngine(
        market_adapter=MarketDataAdapter(),
        news_adapter=NewsDataAdapter(),
        macro_adapter=MacroDataAdapter(),
        mf_adapter=MutualFundAdapter(),
    )


@pytest.fixture
def sample_holdings():
    return [
        Holding(ticker="HDFCBANK", quantity=100, avg_buy_price=1500.0, sector="BANKING"),
        Holding(ticker="TCS", quantity=50, avg_buy_price=3500.0, sector="IT"),
        Holding(ticker="RELIANCE", quantity=30, avg_buy_price=2400.0, sector="ENERGY"),
    ]


@pytest.fixture
def concentrated_holdings():
    return [
        Holding(ticker="HDFCBANK", quantity=1000, avg_buy_price=1500.0, sector="BANKING"),
        Holding(ticker="ICICIBANK", quantity=500, avg_buy_price=900.0, sector="BANKING"),
        Holding(ticker="TCS", quantity=10, avg_buy_price=3500.0, sector="IT"),
    ]


class TestRiskScore:
    def test_zero_hits(self, engine):
        score = engine.risk_score(0, 0, 0, 0)
        assert score.score == 0
        assert all(v == 0 for v in score.breakdown.values())

    def test_max_score_capped_at_100(self, engine):
        score = engine.risk_score(10, 10, 10, 10)
        assert score.score == 100

    def test_individual_category_caps(self, engine):
        score = engine.risk_score(5, 0, 0, 0)
        assert score.breakdown["concentration"] == 40

    def test_breakdown_keys(self, engine):
        score = engine.risk_score(1, 1, 1, 1)
        assert set(score.breakdown.keys()) == {
            "concentration", "overlap", "macro", "sentiment"
        }


class TestPortfolioSummary:
    @pytest.mark.asyncio
    async def test_basic_summary(self, engine, sample_holdings):
        summary, citations = await engine.portfolio_summary(sample_holdings)
        assert "total_value" in summary
        assert "total_pnl" in summary
        assert "positions" in summary
        assert "allocation_by_sector_pct" in summary
        assert len(summary["positions"]) == 3
        assert len(citations) > 0

    @pytest.mark.asyncio
    async def test_sector_allocation_sums_to_100(self, engine, sample_holdings):
        summary, _ = await engine.portfolio_summary(sample_holdings)
        total_pct = sum(summary["allocation_by_sector_pct"].values())
        assert abs(total_pct - 100.0) < 0.1


class TestConcentrationRisk:
    @pytest.mark.asyncio
    async def test_concentrated_portfolio_flags_breaches(self, engine, concentrated_holdings):
        conc, citations, alerts = await engine.concentration_risk(concentrated_holdings)
        assert len(conc["sector_concentration_breaches"]) > 0 or len(conc["stock_concentration_breaches"]) > 0
        assert len(citations) > 0

    @pytest.mark.asyncio
    async def test_top_holdings_sorted(self, engine, sample_holdings):
        conc, _, _ = await engine.concentration_risk(sample_holdings)
        weights = [h["weight_pct"] for h in conc["top_holdings_pct"]]
        assert weights == sorted(weights, reverse=True)


class TestMFOverlap:
    @pytest.mark.asyncio
    async def test_overlap_with_popular_stocks(self, engine, sample_holdings):
        overlap, citations, alerts = await engine.mf_overlap(sample_holdings)
        assert "overlaps" in overlap
        assert len(citations) > 0
        has_overlap = any(
            "HDFCBANK" in o["overlap_tickers"] for o in overlap["overlaps"]
        )
        assert has_overlap, "HDFCBANK should overlap with popular MF schemes"


class TestMacroSensitivity:
    @pytest.mark.asyncio
    async def test_sensitivity_scores(self, engine, sample_holdings):
        macro, citations, alerts = await engine.macro_sensitivity(sample_holdings)
        assert "macro_snapshot" in macro
        assert "holding_exposure" in macro
        assert len(macro["holding_exposure"]) == 3
        for exp in macro["holding_exposure"]:
            assert "sensitivity_score" in exp
            assert exp["sensitivity_score"] >= 3


class TestSentimentShift:
    @pytest.mark.asyncio
    async def test_shift_detection(self, engine, sample_holdings):
        shift, citations, alerts = await engine.sentiment_shift(sample_holdings)
        assert "shifts" in shift
        assert len(shift["shifts"]) == 3
        for s in shift["shifts"]:
            assert "delta" in s
            assert "shift_detected" in s


class TestCrossSourceReport:
    @pytest.mark.asyncio
    async def test_report_structure(self, engine, sample_holdings):
        report, citations, alerts = await engine.cross_source_report(sample_holdings)
        assert "portfolio_summary" in report
        assert "concentration_risk" in report
        assert "mf_overlap" in report
        assert "macro_sensitivity" in report
        assert "sentiment_shift" in report
        assert "cross_source_analysis" in report

        analysis = report["cross_source_analysis"]
        assert "confirmations" in analysis
        assert "contradictions" in analysis
        assert "signals_summary" in analysis
        assert analysis["total_sources_consulted"] == 5

    @pytest.mark.asyncio
    async def test_report_cites_all_sources(self, engine, sample_holdings):
        _, citations, _ = await engine.cross_source_report(sample_holdings)
        assert len(citations) > 0
        sources = {c["source"] for c in citations}
        assert len(sources) >= 3


class TestWhatIfAnalysis:
    @pytest.mark.asyncio
    async def test_rate_cut_scenario(self, engine, sample_holdings):
        result, citations = await engine.what_if_rate_change(sample_holdings, -25)
        assert result["scenario"]["direction"] == "cut"
        assert result["scenario"]["rate_change_bps"] == -25
        assert "portfolio_impact" in result
        assert "holding_impacts" in result
        assert "analysis" in result
        assert len(result["holding_impacts"]) == 3

    @pytest.mark.asyncio
    async def test_rate_hike_scenario(self, engine, sample_holdings):
        result, citations = await engine.what_if_rate_change(sample_holdings, 25)
        assert result["scenario"]["direction"] == "hike"
        assert result["scenario"]["projected_repo_rate"] > result["scenario"]["current_repo_rate"]
