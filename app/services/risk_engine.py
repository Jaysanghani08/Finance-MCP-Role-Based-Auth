from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.adapters.macro_data import MacroDataAdapter
from app.adapters.market_data import MarketDataAdapter
from app.adapters.mf_data import MutualFundAdapter
from app.adapters.news_data import NewsDataAdapter
from app.data.static_reference import SECTOR_SENSITIVITY
from app.models.domain import Alert, Holding, RiskScore


class RiskEngine:
    def __init__(
        self,
        market_adapter: MarketDataAdapter,
        news_adapter: NewsDataAdapter,
        macro_adapter: MacroDataAdapter,
        mf_adapter: MutualFundAdapter,
    ) -> None:
        self.market = market_adapter
        self.news = news_adapter
        self.macro = macro_adapter
        self.mf = mf_adapter

    async def portfolio_summary(self, holdings: list[Holding]) -> tuple[dict, list[dict]]:
        positions = []
        total_value = 0.0
        total_cost = 0.0
        citations: list[dict] = []

        for holding in holdings:
            quote, quote_citations = await self.market.get_quote(holding.ticker)
            market_value = quote["ltp"] * holding.quantity
            cost = holding.avg_buy_price * holding.quantity
            total_value += market_value
            total_cost += cost
            positions.append(
                {
                    "ticker": holding.ticker,
                    "sector": holding.sector,
                    "quantity": holding.quantity,
                    "ltp": quote["ltp"],
                    "market_value": round(market_value, 2),
                    "pnl": round(market_value - cost, 2),
                }
            )
            citations.extend(quote_citations)

        sector_alloc: dict[str, float] = {}
        for p in positions:
            sector_alloc[p["sector"]] = sector_alloc.get(p["sector"], 0.0) + p["market_value"]

        for sector, amount in list(sector_alloc.items()):
            sector_alloc[sector] = round((amount / total_value * 100.0), 2) if total_value else 0.0

        summary = {
            "total_value": round(total_value, 2),
            "total_pnl": round(total_value - total_cost, 2),
            "positions": positions,
            "allocation_by_sector_pct": sector_alloc,
        }
        return summary, citations

    async def concentration_risk(self, holdings: list[Holding]) -> tuple[dict, list[dict], list[Alert]]:
        summary, citations = await self.portfolio_summary(holdings)
        total = summary["total_value"] or 1.0
        stock_concentration = []
        sector_concentration = []
        top_holdings = []
        alerts: list[Alert] = []

        for pos in summary["positions"]:
            weight = round(pos["market_value"] / total * 100.0, 2)
            top_holdings.append({"ticker": pos["ticker"], "weight_pct": weight})
            if weight > 20:
                stock_concentration.append({"ticker": pos["ticker"], "weight_pct": weight})
                alerts.append(
                    Alert(
                        alert_id=str(uuid4()),
                        level="high",
                        category="concentration",
                        message=f"{pos['ticker']} concentration {weight}% exceeds 20% threshold",
                        citations=citations[:1],
                    )
                )

        for sector, pct in summary["allocation_by_sector_pct"].items():
            if pct > 40:
                sector_concentration.append({"sector": sector, "weight_pct": pct})
                alerts.append(
                    Alert(
                        alert_id=str(uuid4()),
                        level="high",
                        category="sector_tilt",
                        message=f"{sector} concentration {pct}% exceeds 40% threshold",
                        citations=citations[:1],
                    )
                )

        top_holdings = sorted(top_holdings, key=lambda x: x["weight_pct"], reverse=True)

        return {
            "stock_concentration_breaches": stock_concentration,
            "sector_concentration_breaches": sector_concentration,
            "top_holdings_pct": top_holdings[:5],
            "sector_exposure_pct": summary["allocation_by_sector_pct"],
        }, citations, alerts

    async def mf_overlap(self, holdings: list[Holding]) -> tuple[dict, list[dict], list[Alert]]:
        holding_set = {h.ticker.upper() for h in holdings}
        funds, citations = await self.mf.get_popular_large_cap_holdings()
        overlaps = []
        alerts: list[Alert] = []
        for scheme, stocks in funds.items():
            common = sorted(list(holding_set.intersection(stocks)))
            if common:
                overlaps.append({"scheme": scheme, "overlap_count": len(common), "overlap_tickers": common})
        if overlaps:
            alerts.append(
                Alert(
                    alert_id=str(uuid4()),
                    level="medium",
                    category="mf_overlap",
                    message="Portfolio overlaps with popular large-cap funds and may duplicate exposure",
                    citations=citations,
                )
            )
        return {"overlaps": overlaps}, citations, alerts

    async def macro_sensitivity(self, holdings: list[Holding]) -> tuple[dict, list[dict], list[Alert]]:
        macro, macro_citations = await self.macro.get_macro_snapshot()
        exposure = []
        alerts: list[Alert] = []
        for h in holdings:
            sens = SECTOR_SENSITIVITY.get(h.sector.upper(), {"rate": 1, "inflation": 1, "forex": 1})
            score = sens["rate"] + sens["inflation"] + sens["forex"]
            exposure.append({"ticker": h.ticker, "sector": h.sector, "sensitivity_score": score})
            if score >= 7:
                alerts.append(
                    Alert(
                        alert_id=str(uuid4()),
                        level="medium",
                        category="macro_sensitivity",
                        message=f"{h.ticker} has elevated macro sensitivity under current conditions",
                        citations=macro_citations,
                    )
                )
        return {"macro_snapshot": macro, "holding_exposure": exposure}, macro_citations, alerts

    async def sentiment_shift(self, holdings: list[Holding]) -> tuple[dict, list[dict], list[Alert]]:
        shifts = []
        citations: list[dict] = []
        alerts: list[Alert] = []
        for h in holdings:
            short, short_c = await self.news.get_sentiment(h.ticker, 7)
            base, base_c = await self.news.get_sentiment(h.ticker, 30)
            delta = round(short["score"] - base["score"], 2)
            shifted = abs(delta) >= 0.4
            shifts.append(
                {
                    "ticker": h.ticker,
                    "sentiment_7d": short["score"],
                    "sentiment_30d": base["score"],
                    "delta": delta,
                    "shift_detected": shifted,
                }
            )
            citations.extend(short_c + base_c)
            if shifted:
                alerts.append(
                    Alert(
                        alert_id=str(uuid4()),
                        level="medium" if delta < 0 else "low",
                        category="sentiment_shift",
                        message=f"{h.ticker} sentiment shifted by {delta} (7d vs 30d baseline)",
                        citations=short_c,
                    )
                )
        return {"shifts": shifts}, citations, alerts

    def risk_score(self, concentration_hits: int, overlap_hits: int, macro_hits: int, sentiment_hits: int) -> RiskScore:
        breakdown = {
            "concentration": min(concentration_hits * 15, 40),
            "overlap": min(overlap_hits * 10, 20),
            "macro": min(macro_hits * 10, 20),
            "sentiment": min(sentiment_hits * 10, 20),
        }
        return RiskScore(score=min(sum(breakdown.values()), 100), breakdown=breakdown)

    async def cross_source_report(self, holdings: list[Holding]) -> tuple[dict, list[dict], list[Alert]]:
        summary, c1 = await self.portfolio_summary(holdings)
        conc, c2, conc_alerts = await self.concentration_risk(holdings)
        overlap, c3, overlap_alerts = await self.mf_overlap(holdings)
        macro, c4, macro_alerts = await self.macro_sensitivity(holdings)
        sentiment, c5, sentiment_alerts = await self.sentiment_shift(holdings)

        confirmations: list[dict] = []
        contradictions: list[dict] = []
        if conc["sector_concentration_breaches"] and overlap["overlaps"]:
            confirmations.append(
                {
                    "finding": "Sector concentration risk is reinforced by MF overlap.",
                    "confirmed_by_sources": ["NSE/yfinance derived allocation", "MFapi overlap"],
                    "evidence": {
                        "sector_breaches": conc["sector_concentration_breaches"],
                        "overlap_count": len(overlap["overlaps"]),
                    },
                }
            )
        if sentiment["shifts"] and macro["macro_snapshot"]["usd_inr_change_30d_pct"] < 0:
            confirmations.append(
                {
                    "finding": "Negative forex trend aligns with sentiment pressure.",
                    "confirmed_by_sources": ["RBI macro snapshot", "News sentiment"],
                    "evidence": {
                        "usd_inr_change_30d_pct": macro["macro_snapshot"]["usd_inr_change_30d_pct"],
                        "shifted_tickers": [s["ticker"] for s in sentiment["shifts"] if s["shift_detected"]],
                    },
                }
            )
        if not conc["stock_concentration_breaches"] and sentiment["shifts"]:
            contradictions.append(
                {
                    "finding": "Sentiment weakness appears without stock concentration stress.",
                    "contradicted_by_sources": ["Portfolio concentration analysis", "News sentiment"],
                    "evidence": {
                        "stock_breaches": conc["stock_concentration_breaches"],
                        "sentiment_shifts": [s for s in sentiment["shifts"] if s["shift_detected"]],
                    },
                }
            )

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "portfolio_summary": summary,
            "concentration_risk": conc,
            "mf_overlap": overlap,
            "macro_sensitivity": macro,
            "sentiment_shift": sentiment,
            "confirmations": confirmations,
            "contradictions": contradictions,
        }
        all_alerts = conc_alerts + overlap_alerts + macro_alerts + sentiment_alerts
        return report, c1 + c2 + c3 + c4 + c5, all_alerts

    async def what_if_rate_change(self, holdings: list[Holding], rate_change_bps: float) -> tuple[dict, list[dict]]:
        hist, citations = await self.macro.get_historical_rate_reaction()
        impact = []
        key = str(int(rate_change_bps))
        for h in holdings:
            sector = h.sector.upper()
            sector_map = hist.get(sector, {})
            pct = sector_map.get(key, 0.0)
            impact.append({"ticker": h.ticker, "sector": h.sector, "estimated_price_impact_pct": pct})
        return {"rate_change_bps": rate_change_bps, "holding_impacts": impact}, citations

