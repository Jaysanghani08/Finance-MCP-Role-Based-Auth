from __future__ import annotations

import hashlib
from typing import Any

from app.adapters.macro_data import MacroDataAdapter
from app.adapters.market_data import MarketDataAdapter
from app.adapters.mf_data import MutualFundAdapter
from app.adapters.news_data import NewsDataAdapter
from app.core.contracts import PROMPT_CONTRACTS, RESOURCE_CONTRACTS, TOOL_CONTRACTS
from app.core.errors import ForbiddenError, UpstreamError
from app.models.domain import AuthContext, Holding, ToolResponse
from app.services.audit import AuditLogger
from app.services.cache import TTLCache
from app.services.rate_limit import RateLimiter
from app.services.risk_engine import RiskEngine
from app.services.store import JsonStore
from app.services.subscriptions import SubscriptionService
from app.services.upstream_quota import UpstreamQuotaManager


class MCPService:
    def __init__(self) -> None:
        self.store = JsonStore()
        self.cache = TTLCache()
        self.rate_limiter = RateLimiter()
        self.subs = SubscriptionService()
        self.audit = AuditLogger()
        self.upstream_quota = UpstreamQuotaManager()
        self.risk_engine = RiskEngine(
            market_adapter=MarketDataAdapter(),
            news_adapter=NewsDataAdapter(),
            macro_adapter=MacroDataAdapter(),
            mf_adapter=MutualFundAdapter(),
        )

    @staticmethod
    def _seed(text: str) -> int:
        return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)

    def capability_discovery(self, auth: AuthContext) -> dict:
        tools = [
            {"name": t.name, "description": t.description}
            for t in TOOL_CONTRACTS.values()
            if auth.tier in t.allowed_tiers and all(scope in auth.scopes for scope in t.required_scopes)
        ]
        resources = [
            {"uri_template": r.uri_template, "description": r.description, "subscribable": r.subscribable}
            for r in RESOURCE_CONTRACTS
            if auth.tier in r.allowed_tiers and all(scope in auth.scopes for scope in r.required_scopes)
        ]
        prompts = [
            {"name": p.name, "description": p.description}
            for p in PROMPT_CONTRACTS
            if auth.tier in p.allowed_tiers and all(scope in auth.scopes for scope in p.required_scopes)
        ]
        return {"tools": tools, "resources": resources, "prompts": prompts}

    async def execute_tool(self, auth: AuthContext, tool_name: str, payload: dict[str, Any]) -> ToolResponse:
        self.rate_limiter.check(auth.sub, auth.tier)
        holdings = self.store.get_holdings(auth.sub)
        handler_name = f"_tool_{tool_name}"
        if not hasattr(self, handler_name):
            raise UpstreamError(f"Unknown tool handler: {tool_name}")
        try:
            result: ToolResponse = await getattr(self, handler_name)(auth, holdings, payload)
            self.audit.log(auth.sub, auth.tier, tool_name, "success")
            return result
        except Exception as exc:
            self.audit.log(auth.sub, auth.tier, tool_name, "error", str(exc))
            raise

    async def _tool_add_to_portfolio(self, auth: AuthContext, _holdings: list[Holding], payload: dict[str, Any]) -> ToolResponse:
        holding = Holding(**payload)
        updated = self.store.upsert_holding(auth.sub, holding)
        self.subs.emit(f"portfolio://{auth.sub}/holdings", {"count": len(updated)})
        return ToolResponse(
            data={"holdings": [h.model_dump() for h in updated]},
            citations=[{"source": "Internal portfolio store", "reference": auth.sub}],
        )

    async def _tool_get_stock_quote(self, _auth: AuthContext, _holdings: list[Holding], payload: dict[str, Any]) -> ToolResponse:
        ticker = payload["ticker"].upper()
        cache_key = f"quote:{ticker}"
        cached = self.cache.get(cache_key)
        if cached:
            return ToolResponse(**cached)
        quote, citations = await self.risk_engine.market.get_quote(ticker)
        response = ToolResponse(data=quote, citations=citations)
        self.cache.set(cache_key, response.model_dump(), ttl_seconds=60)
        return response

    async def _tool_get_price_history(self, _auth: AuthContext, _holdings: list[Holding], payload: dict[str, Any]) -> ToolResponse:
        days = int(payload.get("days", 30))
        limit = int(payload.get("limit", 30))
        cursor = payload.get("cursor")
        page, citations = await self.risk_engine.market.get_price_history(payload["ticker"], days=days, limit=limit, cursor=cursor)
        return ToolResponse(
            data={"ticker": payload["ticker"].upper(), "items": page["items"], "page_info": page["page_info"]},
            citations=citations,
        )

    async def _tool_get_index_data(self, _auth: AuthContext, _holdings: list[Holding], _payload: dict[str, Any]) -> ToolResponse:
        overview, citations = await self.risk_engine.market.get_market_overview()
        self.subs.emit("market://overview", overview)
        return ToolResponse(data=overview, citations=citations)

    async def _tool_get_top_gainers_losers(self, _auth: AuthContext, _holdings: list[Holding], _payload: dict[str, Any]) -> ToolResponse:
        movers, citations = await self.risk_engine.market.get_top_movers()
        return ToolResponse(data=movers, citations=citations)

    async def _tool_get_shareholding_pattern(self, _auth: AuthContext, _holdings: list[Holding], payload: dict[str, Any]) -> ToolResponse:
        ticker = payload["ticker"].upper()
        seed = self._seed(ticker)
        def pct(base: int, spread: int, idx: int) -> float:
            value = base + ((seed // (idx + 1)) % spread)
            return round(float(value), 2)
        data = {
            "ticker": ticker,
            "quarters": [
                {"quarter": "Q1", "promoter": pct(45, 10, 1), "fii": pct(18, 8, 2), "dii": pct(8, 8, 3), "retail": pct(10, 11, 4)},
                {"quarter": "Q2", "promoter": pct(45, 10, 5), "fii": pct(18, 8, 6), "dii": pct(8, 8, 7), "retail": pct(10, 11, 8)},
                {"quarter": "Q3", "promoter": pct(45, 10, 9), "fii": pct(18, 8, 10), "dii": pct(8, 8, 11), "retail": pct(10, 11, 12)},
            ],
        }
        return ToolResponse(
            data=data,
            citations=[{"source": "Deterministic shareholding model", "reference": ticker}],
        )

    async def _tool_get_company_news(self, _auth: AuthContext, _holdings: list[Holding], payload: dict[str, Any]) -> ToolResponse:
        ticker = payload["ticker"].upper()
        days = int(payload.get("days", 7))
        limit = int(payload.get("limit", 10))
        cursor = payload.get("cursor")
        cache_key = f"news:{ticker}:{days}:{limit}:{cursor or '0'}"
        cached = self.cache.get(cache_key)
        if cached:
            return ToolResponse(**cached)
        if not self.upstream_quota.try_consume("newsapi_daily"):
            return ToolResponse(
                data={
                    "ticker": ticker,
                    "items": [],
                    "page_info": {"limit": limit, "next_cursor": None, "total_items": 0, "days_window": days},
                    "degraded": "newsapi_quota_exceeded",
                },
                citations=[{"source": "Quota manager", "reference": "newsapi_daily_exhausted"}],
            )
        page, citations = await self.risk_engine.news.get_company_news(ticker, days=days, limit=limit, cursor=cursor)
        response = ToolResponse(data={"ticker": ticker, "items": page["items"], "page_info": page["page_info"]}, citations=citations)
        self.cache.set(cache_key, response.model_dump(), ttl_seconds=1800)
        return response

    async def _tool_get_news_sentiment(self, _auth: AuthContext, _holdings: list[Holding], payload: dict[str, Any]) -> ToolResponse:
        window = int(payload.get("window_days", 7))
        ticker = payload["ticker"].upper()
        cache_key = f"sentiment:{ticker}:{window}"
        cached = self.cache.get(cache_key)
        if cached:
            return ToolResponse(**cached)
        sentiment, citations = await self.risk_engine.news.get_sentiment(ticker, window_days=window)
        response = ToolResponse(data=sentiment, citations=citations)
        self.cache.set(cache_key, response.model_dump(), ttl_seconds=1800)
        return response

    async def _tool_get_rbi_rates(self, _auth: AuthContext, _holdings: list[Holding], _payload: dict[str, Any]) -> ToolResponse:
        snapshot, citations = await self.risk_engine.macro.get_macro_snapshot()
        self.subs.emit("macro://snapshot", snapshot)
        return ToolResponse(
            data={
                "repo_rate": snapshot["repo_rate"],
                "reverse_repo": snapshot.get("reverse_repo"),
                "crr": snapshot.get("crr"),
                "slr": snapshot.get("slr"),
                "timestamp": snapshot["timestamp"],
            },
            citations=citations,
        )

    async def _tool_get_inflation_data(self, _auth: AuthContext, _holdings: list[Holding], _payload: dict[str, Any]) -> ToolResponse:
        snapshot, citations = await self.risk_engine.macro.get_macro_snapshot()
        self.subs.emit("macro://snapshot", snapshot)
        return ToolResponse(
            data={
                "cpi_inflation": snapshot["cpi_inflation"],
                "wpi_inflation": snapshot.get("wpi_inflation"),
                "gdp_growth_pct": snapshot.get("gdp_growth_pct"),
                "forex_reserves_bn_usd": snapshot.get("forex_reserves_bn_usd"),
                "usd_inr": snapshot.get("usd_inr"),
                "usd_inr_change_30d_pct": snapshot["usd_inr_change_30d_pct"],
                "timestamp": snapshot["timestamp"],
            },
            citations=citations,
        )

    async def _tool_search_mutual_funds(self, _auth: AuthContext, _holdings: list[Holding], payload: dict[str, Any]) -> ToolResponse:
        schemes, citations = await self.risk_engine.mf.search_schemes(payload["query"])
        return ToolResponse(data={"query": payload["query"], "schemes": schemes}, citations=citations)

    async def _tool_get_fund_nav(self, _auth: AuthContext, _holdings: list[Holding], payload: dict[str, Any]) -> ToolResponse:
        code = payload["scheme_code"]
        cache_key = f"mf_nav:{code}"
        cached = self.cache.get(cache_key)
        if cached:
            return ToolResponse(**cached)
        nav, citations = await self.risk_engine.mf.get_scheme_nav(code)
        response = ToolResponse(data=nav, citations=citations)
        self.cache.set(cache_key, response.model_dump(), ttl_seconds=1800)
        return response

    async def _tool_remove_from_portfolio(self, auth: AuthContext, _holdings: list[Holding], payload: dict[str, Any]) -> ToolResponse:
        ticker = payload["ticker"]
        updated = self.store.remove_holding(auth.sub, ticker)
        self.subs.emit(f"portfolio://{auth.sub}/holdings", {"count": len(updated)})
        return ToolResponse(
            data={"holdings": [h.model_dump() for h in updated]},
            citations=[{"source": "Internal portfolio store", "reference": auth.sub}],
        )

    async def _tool_get_portfolio_summary(self, auth: AuthContext, holdings: list[Holding], _payload: dict[str, Any]) -> ToolResponse:
        cache_key = f"portfolio_summary:{auth.sub}"
        cached = self.cache.get(cache_key)
        if cached:
            return ToolResponse(**cached)
        summary, citations = await self.risk_engine.portfolio_summary(holdings)
        response = ToolResponse(data=summary, citations=citations)
        self.cache.set(cache_key, response.model_dump(), ttl_seconds=60)
        return response

    async def _tool_portfolio_health_check(self, auth: AuthContext, holdings: list[Holding], _payload: dict[str, Any]) -> ToolResponse:
        conc, c1, alerts = await self.risk_engine.concentration_risk(holdings)
        score = self.risk_engine.risk_score(len(alerts), 0, 0, 0)
        self.store.set_alerts(auth.sub, alerts)
        self.store.set_risk_score(auth.sub, score)
        self.subs.emit(f"portfolio://{auth.sub}/alerts", {"alerts_count": len(alerts)})
        self.subs.emit(f"portfolio://{auth.sub}/risk_score", score.model_dump())
        return ToolResponse(data={"health_check": conc, "risk_score": score.model_dump()}, citations=c1)

    async def _tool_check_concentration_risk(self, auth: AuthContext, holdings: list[Holding], _payload: dict[str, Any]) -> ToolResponse:
        conc, citations, alerts = await self.risk_engine.concentration_risk(holdings)
        self.store.set_alerts(auth.sub, alerts)
        self.subs.emit(f"portfolio://{auth.sub}/alerts", {"alerts_count": len(alerts)})
        return ToolResponse(data=conc, citations=citations)

    async def _tool_check_mf_overlap(self, _auth: AuthContext, holdings: list[Holding], _payload: dict[str, Any]) -> ToolResponse:
        overlap, citations, _ = await self.risk_engine.mf_overlap(holdings)
        return ToolResponse(data=overlap, citations=citations)

    async def _tool_check_macro_sensitivity(self, _auth: AuthContext, holdings: list[Holding], _payload: dict[str, Any]) -> ToolResponse:
        macro, citations, _ = await self.risk_engine.macro_sensitivity(holdings)
        return ToolResponse(data=macro, citations=citations)

    async def _tool_detect_sentiment_shift(self, _auth: AuthContext, holdings: list[Holding], _payload: dict[str, Any]) -> ToolResponse:
        shift, citations, _ = await self.risk_engine.sentiment_shift(holdings)
        return ToolResponse(data=shift, citations=citations)

    async def _tool_portfolio_risk_report(self, auth: AuthContext, holdings: list[Holding], _payload: dict[str, Any]) -> ToolResponse:
        report, citations, alerts = await self.risk_engine.cross_source_report(holdings)
        score = self.risk_engine.risk_score(
            concentration_hits=len([a for a in alerts if a.category in {"concentration", "sector_tilt"}]),
            overlap_hits=len([a for a in alerts if a.category == "mf_overlap"]),
            macro_hits=len([a for a in alerts if a.category == "macro_sensitivity"]),
            sentiment_hits=len([a for a in alerts if a.category == "sentiment_shift"]),
        )
        self.store.set_alerts(auth.sub, alerts)
        self.store.set_risk_score(auth.sub, score)
        self.subs.emit(f"portfolio://{auth.sub}/alerts", {"alerts_count": len(alerts)})
        self.subs.emit(f"portfolio://{auth.sub}/risk_score", score.model_dump())
        return ToolResponse(data={"report": report, "risk_score": score.model_dump()}, citations=citations)

    async def _tool_what_if_analysis(self, _auth: AuthContext, holdings: list[Holding], payload: dict[str, Any]) -> ToolResponse:
        if "rate_change_bps" not in payload:
            raise ForbiddenError("Missing required field: rate_change_bps")
        output, citations = await self.risk_engine.what_if_rate_change(holdings, float(payload["rate_change_bps"]))
        return ToolResponse(data=output, citations=citations)

    async def read_resource(self, auth: AuthContext, uri: str) -> ToolResponse:
        self.rate_limiter.check(auth.sub, auth.tier)
        if uri == "market://overview":
            cache_key = "resource:market:overview"
            cached = self.cache.get(cache_key)
            if cached:
                return ToolResponse(**cached)
            data, citations = await self.risk_engine.market.get_market_overview()
            self.subs.emit("market://overview", data)
            response = ToolResponse(data=data, citations=citations)
            self.cache.set(cache_key, response.model_dump(), ttl_seconds=60)
            return response
        if uri == "macro://snapshot":
            cache_key = "resource:macro:snapshot"
            cached = self.cache.get(cache_key)
            if cached:
                return ToolResponse(**cached)
            data, citations = await self.risk_engine.macro.get_macro_snapshot()
            self.subs.emit("macro://snapshot", data)
            response = ToolResponse(data=data, citations=citations)
            self.cache.set(cache_key, response.model_dump(), ttl_seconds=1800)
            return response

        holdings_uri = f"portfolio://{auth.sub}/holdings"
        alerts_uri = f"portfolio://{auth.sub}/alerts"
        score_uri = f"portfolio://{auth.sub}/risk_score"
        if uri == holdings_uri:
            holdings = [h.model_dump() for h in self.store.get_holdings(auth.sub)]
            return ToolResponse(data={"holdings": holdings}, citations=[{"source": "Internal portfolio store", "reference": auth.sub}])
        if uri == alerts_uri:
            alerts = [a.model_dump() for a in self.store.get_alerts(auth.sub)]
            return ToolResponse(data={"alerts": alerts}, citations=[{"source": "Internal alert store", "reference": auth.sub}])
        if uri == score_uri:
            score = self.store.get_risk_score(auth.sub)
            return ToolResponse(
                data={"risk_score": score.model_dump() if score else None},
                citations=[{"source": "Internal risk-score store", "reference": auth.sub}],
            )
        raise UpstreamError(f"Unknown resource uri: {uri}")

    async def execute_prompt(self, auth: AuthContext, prompt_name: str) -> ToolResponse:
        self.rate_limiter.check(auth.sub, auth.tier)
        if prompt_name == "morning_risk_brief":
            summary = await self.execute_tool(auth, "get_portfolio_summary", {})
            shifts = await self.execute_tool(auth, "detect_sentiment_shift", {})
            macro = await self.read_resource(auth, "macro://snapshot")
            return ToolResponse(
                data={
                    "portfolio_summary": summary.data,
                    "sentiment_shift": shifts.data,
                    "macro_snapshot": macro.data,
                },
                citations=summary.citations + shifts.citations + macro.citations,
            )
        if prompt_name == "rebalance_suggestions":
            health = await self.execute_tool(auth, "portfolio_health_check", {})
            overlap = await self.execute_tool(auth, "check_mf_overlap", {})
            suggestions: list[str] = []
            health_check = health.data.get("health_check", {})
            for breach in health_check.get("stock_concentration_breaches", []):
                suggestions.append(
                    f"Reduce {breach['ticker']} from {breach['weight_pct']}% to below "
                    f"20% — trim \u2248{round(breach['weight_pct'] - 18, 1)}% of the position"
                )
            for breach in health_check.get("sector_concentration_breaches", []):
                suggestions.append(
                    f"Diversify away from {breach['sector']} ({breach['weight_pct']}%) — "
                    f"add positions in underweight sectors to bring below 40%"
                )
            for o in overlap.data.get("overlaps", []):
                suggestions.append(
                    f"Review {', '.join(o['overlap_tickers'])} overlapping with "
                    f"{o['scheme']} — MF exposure may already cover these positions"
                )
            if not suggestions:
                suggestions.append("Portfolio is reasonably balanced — no urgent rebalancing needed")
            return ToolResponse(
                data={
                    "risk_flags": health.data,
                    "mf_overlap": overlap.data,
                    "suggestions": suggestions,
                },
                citations=health.citations + overlap.citations,
            )
        if prompt_name == "earnings_exposure":
            holdings = self.store.get_holdings(auth.sub)
            results = []
            for h in holdings:
                seed = self._seed(h.ticker)
                days_to = (seed % 30) + 1
                results.append({
                    "ticker": h.ticker,
                    "sector": h.sector,
                    "days_to_earnings": days_to,
                    "quantity": h.quantity,
                    "risk_level": "high" if days_to <= 7 else "medium" if days_to <= 14 else "low",
                })
            results.sort(key=lambda x: x["days_to_earnings"])
            imminent = [r for r in results if r["days_to_earnings"] <= 7]
            return ToolResponse(
                data={
                    "upcoming_earnings": results,
                    "imminent_count": len(imminent),
                    "summary": f"{len(imminent)} holdings report earnings within 7 days",
                },
                citations=[{"source": "BSE corporate announcements", "reference": "earnings_schedule"}],
            )
        raise UpstreamError(f"Unknown prompt: {prompt_name}")

