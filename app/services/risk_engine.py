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

        overlap_tickers: set[str] = set()
        for o in overlap.get("overlaps", []):
            overlap_tickers.update(o.get("overlap_tickers", []))

        shifted_tickers = [s["ticker"] for s in sentiment["shifts"] if s["shift_detected"]]
        negative_shifts = [s for s in sentiment["shifts"] if s["shift_detected"] and s["delta"] < 0]
        positive_shifts = [s for s in sentiment["shifts"] if s["shift_detected"] and s["delta"] > 0]

        fx_change = macro["macro_snapshot"].get("usd_inr_change_30d_pct", 0)
        repo_rate = macro["macro_snapshot"].get("repo_rate", 0)
        it_exposure = summary["allocation_by_sector_pct"].get("IT", 0)
        banking_exposure = summary["allocation_by_sector_pct"].get("BANKING", 0)

        high_sensitivity = [
            e for e in macro["holding_exposure"] if e["sensitivity_score"] >= 7
        ]

        if conc["sector_concentration_breaches"] and overlap["overlaps"]:
            confirmations.append({
                "finding": (
                    "Sector concentration risk is reinforced by mutual fund overlap — "
                    "your portfolio duplicates exposure that popular large-cap MF schemes also hold."
                ),
                "confirmed_by_sources": ["NSE/yfinance (derived allocation)", "MFapi.in (popular fund holdings)"],
                "evidence": {
                    "sector_breaches": conc["sector_concentration_breaches"],
                    "overlap_count": len(overlap["overlaps"]),
                    "overlapping_tickers": sorted(overlap_tickers),
                },
            })

        if it_exposure > 15 and fx_change < -1:
            confirmations.append({
                "finding": (
                    f"IT sector is {it_exposure}% of portfolio while INR strengthened "
                    f"{abs(fx_change)}% over 30 days — this historically pressures IT "
                    "export margins and rupee-denominated revenue."
                ),
                "confirmed_by_sources": ["NSE/yfinance (IT allocation derived)", "RBI DBIE (USD-INR movement)"],
                "evidence": {"it_allocation_pct": it_exposure, "usd_inr_change_30d_pct": fx_change},
            })

        if banking_exposure > 15 and repo_rate >= 6.0:
            confirmations.append({
                "finding": (
                    f"Banking sector is {banking_exposure}% of portfolio with repo rate at "
                    f"{repo_rate}% — elevated rates squeeze net interest margins for "
                    "banks while benefiting deposit income; monitor for rate-cut signals."
                ),
                "confirmed_by_sources": ["NSE/yfinance (banking allocation)", "RBI DBIE (repo rate)"],
                "evidence": {"banking_allocation_pct": banking_exposure, "repo_rate_pct": repo_rate},
            })

        if negative_shifts and fx_change < -1:
            confirmations.append({
                "finding": (
                    "Negative forex trend aligns with deteriorating news sentiment — "
                    "macro headwinds may be driving company-level pessimism."
                ),
                "confirmed_by_sources": ["RBI DBIE (forex movement)", "NewsAPI (sentiment analysis)"],
                "evidence": {
                    "usd_inr_change_30d_pct": fx_change,
                    "negatively_shifted_tickers": [s["ticker"] for s in negative_shifts],
                    "avg_sentiment_delta": round(
                        sum(s["delta"] for s in negative_shifts) / len(negative_shifts), 2
                    ),
                },
            })

        if len(high_sensitivity) >= 2:
            confirmations.append({
                "finding": (
                    f"{len(high_sensitivity)} holdings have elevated macro sensitivity "
                    f"(score ≥ 7) — portfolio is broadly vulnerable to RBI policy "
                    "changes, inflation shifts, and forex movements."
                ),
                "confirmed_by_sources": ["Sector sensitivity model", "RBI DBIE (current macro conditions)"],
                "evidence": {
                    "high_sensitivity_holdings": [
                        {"ticker": e["ticker"], "score": e["sensitivity_score"]}
                        for e in high_sensitivity
                    ],
                },
            })

        doubly_exposed = sorted(overlap_tickers.intersection(shifted_tickers))
        if doubly_exposed:
            confirmations.append({
                "finding": (
                    f"Stocks {', '.join(doubly_exposed)} appear in both MF overlap and "
                    "sentiment-shift lists — popular names face compounding risk from "
                    "broad market selling and sentiment deterioration."
                ),
                "confirmed_by_sources": ["MFapi.in (fund overlap)", "NewsAPI (sentiment analysis)"],
                "evidence": {"doubly_exposed_tickers": doubly_exposed},
            })

        if not conc["stock_concentration_breaches"] and negative_shifts:
            contradictions.append({
                "finding": (
                    "News sentiment has turned negative for some holdings, but no single "
                    "stock breaches the 20% concentration threshold — the negative "
                    "sentiment may be market-wide rather than portfolio-specific."
                ),
                "contradicted_by_sources": [
                    "Portfolio concentration analysis (NSE/yfinance)",
                    "NewsAPI (sentiment analysis)",
                ],
                "evidence": {
                    "stock_breaches_count": 0,
                    "negative_sentiment_tickers": [s["ticker"] for s in negative_shifts],
                },
            })

        if repo_rate <= 6.5 and fx_change >= 0 and negative_shifts and not positive_shifts:
            contradictions.append({
                "finding": (
                    "Macro environment appears stable (repo rate steady, INR stable or "
                    "appreciating) but sentiment is deteriorating — pessimism may be "
                    "event-driven and potentially transient rather than macro-fundamental."
                ),
                "contradicted_by_sources": ["RBI DBIE (macro stability)", "NewsAPI (sentiment analysis)"],
                "evidence": {
                    "repo_rate": repo_rate,
                    "usd_inr_change_30d_pct": fx_change,
                    "negative_sentiment_count": len(negative_shifts),
                },
            })

        if conc["sector_concentration_breaches"] and not overlap["overlaps"]:
            contradictions.append({
                "finding": (
                    "Portfolio has sector concentration risk but holdings do not overlap "
                    "with popular large-cap MF schemes — your sector bet is differentiated "
                    "from mainstream institutional positioning."
                ),
                "contradicted_by_sources": [
                    "Portfolio concentration analysis",
                    "MFapi.in (no fund overlap detected)",
                ],
                "evidence": {
                    "concentrated_sectors": [
                        b["sector"] for b in conc["sector_concentration_breaches"]
                    ],
                    "mf_overlaps_found": 0,
                },
            })

        low_sensitivity_all = all(
            e["sensitivity_score"] < 5 for e in macro["holding_exposure"]
        ) if macro["holding_exposure"] else True
        if conc["stock_concentration_breaches"] and low_sensitivity_all:
            contradictions.append({
                "finding": (
                    "Portfolio has stock concentration risk but low macro sensitivity "
                    "across all holdings — risk is idiosyncratic (company-specific) "
                    "rather than systemic (macro-driven)."
                ),
                "contradicted_by_sources": [
                    "Portfolio concentration analysis",
                    "Sector sensitivity model",
                ],
                "evidence": {
                    "concentrated_stocks": [
                        b["ticker"] for b in conc["stock_concentration_breaches"]
                    ],
                    "max_macro_sensitivity": max(
                        (e["sensitivity_score"] for e in macro["holding_exposure"]), default=0
                    ),
                },
            })

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "portfolio_summary": summary,
            "concentration_risk": conc,
            "mf_overlap": overlap,
            "macro_sensitivity": macro,
            "sentiment_shift": sentiment,
            "cross_source_analysis": {
                "total_sources_consulted": 5,
                "sources": [
                    "NSE/yfinance (market data and derived allocation)",
                    "MFapi.in (mutual fund overlap)",
                    "RBI DBIE (macro indicators)",
                    "NewsAPI (sentiment analysis)",
                    "Sector sensitivity model (derived)",
                ],
                "confirmations": confirmations,
                "contradictions": contradictions,
                "signals_summary": {
                    "confirming_signals": len(confirmations),
                    "contradicting_signals": len(contradictions),
                    "net_risk_direction": (
                        "elevated" if len(confirmations) > len(contradictions) else "mixed"
                    ),
                },
            },
        }
        all_alerts = conc_alerts + overlap_alerts + macro_alerts + sentiment_alerts
        return report, c1 + c2 + c3 + c4 + c5, all_alerts

    async def what_if_rate_change(
        self, holdings: list[Holding], rate_change_bps: float
    ) -> tuple[dict, list[dict]]:
        hist, hist_citations = await self.macro.get_historical_rate_reaction()
        macro_snapshot, macro_citations = await self.macro.get_macro_snapshot()
        summary, summary_citations = await self.portfolio_summary(holdings)

        total_value = summary["total_value"] or 1.0
        impact = []
        weighted_impact_sum = 0.0
        key = str(int(rate_change_bps))

        for pos in summary["positions"]:
            sector = pos["sector"].upper()
            sector_map = hist.get(sector, {})
            pct = sector_map.get(key, 0.0)
            value_change = round(pos["market_value"] * pct / 100.0, 2)
            weight = pos["market_value"] / total_value
            weighted_impact_sum += weight * pct
            impact.append({
                "ticker": pos["ticker"],
                "sector": pos["sector"],
                "current_value": pos["market_value"],
                "estimated_price_impact_pct": pct,
                "estimated_value_change": value_change,
                "portfolio_weight_pct": round(weight * 100, 2),
            })

        projected_rate = macro_snapshot["repo_rate"] + (rate_change_bps / 100.0)
        direction = "cut" if rate_change_bps < 0 else "hike"
        total_impact_pct = round(weighted_impact_sum, 2)
        total_value_change = round(total_value * total_impact_pct / 100.0, 2)

        beneficiaries = sorted(
            [i for i in impact if i["estimated_price_impact_pct"] > 0],
            key=lambda x: x["estimated_price_impact_pct"], reverse=True,
        )
        adversely_affected = sorted(
            [i for i in impact if i["estimated_price_impact_pct"] < 0],
            key=lambda x: x["estimated_price_impact_pct"],
        )

        return {
            "scenario": {
                "rate_change_bps": rate_change_bps,
                "direction": direction,
                "current_repo_rate": macro_snapshot["repo_rate"],
                "projected_repo_rate": round(projected_rate, 2),
            },
            "portfolio_impact": {
                "current_total_value": total_value,
                "weighted_impact_pct": total_impact_pct,
                "estimated_total_value_change": total_value_change,
            },
            "holding_impacts": impact,
            "analysis": {
                "beneficiaries": [
                    {"ticker": b["ticker"], "impact_pct": b["estimated_price_impact_pct"]}
                    for b in beneficiaries[:3]
                ],
                "adversely_affected": [
                    {"ticker": a["ticker"], "impact_pct": a["estimated_price_impact_pct"]}
                    for a in adversely_affected[:3]
                ],
                "narrative": (
                    f"A {abs(int(rate_change_bps))}bps rate {direction} (repo "
                    f"{macro_snapshot['repo_rate']}% \u2192 {round(projected_rate, 2)}%) "
                    f"would have a net {total_impact_pct}% impact on portfolio value "
                    f"(\u2248 \u20b9{total_value_change:,.0f} change). "
                    f"Based on historical sector reactions to past RBI rate {direction}s."
                ),
            },
        }, hist_citations + macro_citations + summary_citations

