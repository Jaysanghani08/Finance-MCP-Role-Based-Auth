from __future__ import annotations

from typing import Any
from random import uniform

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
        quote, citations = await self.risk_engine.market.get_quote(payload["ticker"])
        return ToolResponse(data=quote, citations=citations)

    async def _tool_get_price_history(self, _auth: AuthContext, _holdings: list[Holding], payload: dict[str, Any]) -> ToolResponse:
        days = int(payload.get("days", 30))
        rows, citations = await self.risk_engine.market.get_price_history(payload["ticker"], days=days)
        return ToolResponse(data={"ticker": payload["ticker"].upper(), "rows": rows}, citations=citations)

    async def _tool_get_index_data(self, _auth: AuthContext, _holdings: list[Holding], _payload: dict[str, Any]) -> ToolResponse:
        overview, citations = await self.risk_engine.market.get_market_overview()
        return ToolResponse(data=overview, citations=citations)

    async def _tool_get_top_gainers_losers(self, _auth: AuthContext, _holdings: list[Holding], _payload: dict[str, Any]) -> ToolResponse:
        movers, citations = await self.risk_engine.market.get_top_movers()
        return ToolResponse(data=movers, citations=citations)

    async def _tool_get_shareholding_pattern(self, _auth: AuthContext, _holdings: list[Holding], payload: dict[str, Any]) -> ToolResponse:
        ticker = payload["ticker"].upper()
        data = {
            "ticker": ticker,
            "quarters": [
                {"quarter": "Q1", "promoter": round(uniform(45, 55), 2), "fii": round(uniform(18, 25), 2), "dii": round(uniform(8, 15), 2), "retail": round(uniform(10, 20), 2)},
                {"quarter": "Q2", "promoter": round(uniform(45, 55), 2), "fii": round(uniform(18, 25), 2), "dii": round(uniform(8, 15), 2), "retail": round(uniform(10, 20), 2)},
                {"quarter": "Q3", "promoter": round(uniform(45, 55), 2), "fii": round(uniform(18, 25), 2), "dii": round(uniform(8, 15), 2), "retail": round(uniform(10, 20), 2)},
            ],
        }
        return ToolResponse(
            data=data,
            citations=[{"source": "Shareholding model (demo dataset)", "reference": ticker}],
        )

    async def _tool_get_company_news(self, _auth: AuthContext, _holdings: list[Holding], payload: dict[str, Any]) -> ToolResponse:
        ticker = payload["ticker"].upper()
        cache_key = f"news:{ticker}"
        cached = self.cache.get(cache_key)
        if cached:
            return ToolResponse(**cached)
        if not self.upstream_quota.try_consume("newsapi_daily"):
            return ToolResponse(
                data={"ticker": ticker, "articles": [], "degraded": "newsapi_quota_exceeded"},
                citations=[{"source": "Quota manager", "reference": "newsapi_daily_exhausted"}],
            )
        articles, citations = await self.risk_engine.news.get_company_news(ticker)
        response = ToolResponse(data={"ticker": ticker, "articles": articles}, citations=citations)
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
        return ToolResponse(data={"repo_rate": snapshot["repo_rate"], "timestamp": snapshot["timestamp"]}, citations=citations)

    async def _tool_get_inflation_data(self, _auth: AuthContext, _holdings: list[Holding], _payload: dict[str, Any]) -> ToolResponse:
        snapshot, citations = await self.risk_engine.macro.get_macro_snapshot()
        return ToolResponse(
            data={
                "cpi_inflation": snapshot["cpi_inflation"],
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
            response = ToolResponse(data=data, citations=citations)
            self.cache.set(cache_key, response.model_dump(), ttl_seconds=60)
            return response
        if uri == "macro://snapshot":
            cache_key = "resource:macro:snapshot"
            cached = self.cache.get(cache_key)
            if cached:
                return ToolResponse(**cached)
            data, citations = await self.risk_engine.macro.get_macro_snapshot()
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
            return ToolResponse(
                data={
                    "risk_flags": health.data,
                    "suggestions": [
                        "Reduce weights in positions crossing threshold",
                        "Diversify across sectors below 15% allocation",
                        "Trim holdings that duplicate MF large-cap exposure",
                    ],
                },
                citations=health.citations,
            )
        if prompt_name == "earnings_exposure":
            holdings = self.store.get_holdings(auth.sub)
            data = {"upcoming_earnings": [{"ticker": h.ticker, "days_to_earnings": 7} for h in holdings]}
            return ToolResponse(
                data=data,
                citations=[{"source": "Earnings placeholder schedule", "reference": "mock_calendar"}],
            )
        raise UpstreamError(f"Unknown prompt: {prompt_name}")

