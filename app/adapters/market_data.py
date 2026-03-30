from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from datetime import timedelta

import httpx


class MarketDataAdapter:
    """
    Market adapter with best-effort yfinance endpoint and deterministic fallback.
    """

    @staticmethod
    def _seed(text: str) -> int:
        return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)

    @classmethod
    def _deterministic_quote(cls, symbol: str) -> dict:
        seed = cls._seed(symbol)
        ltp = round(100 + (seed % 240000) / 100.0, 2)
        change_raw = ((seed // 13) % 700) / 100.0
        change_pct = round(change_raw - 3.5, 2)
        volume = 100000 + (seed % 4900000)
        return {
            "ticker": symbol,
            "ltp": ltp,
            "change_pct": change_pct,
            "volume": volume,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_quote(self, ticker: str) -> tuple[dict, list[dict]]:
        symbol = ticker.upper().replace(".NS", "")
        sources: list[dict] = []
        try:
            url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}.NS"
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                results = resp.json().get("quoteResponse", {}).get("result", [])
                if not results:
                    raise ValueError("No quote rows returned from upstream")
                result = results[0]
            data = {
                "ticker": symbol,
                "ltp": float(result.get("regularMarketPrice") or 0),
                "change_pct": float(result.get("regularMarketChangePercent") or 0),
                "volume": int(result.get("regularMarketVolume") or 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            sources.append(
                {
                    "source": "yfinance",
                    "reference": f"{symbol}.NS",
                    "as_of": data["timestamp"],
                }
            )
            return data, sources
        except Exception:
            data = self._deterministic_quote(symbol)
            sources.append(
                {
                    "source": "Deterministic market fallback",
                    "reference": f"{symbol}",
                    "as_of": data["timestamp"],
                }
            )
            return data, sources

    async def get_market_overview(self) -> tuple[dict, list[dict]]:
        nifty, nse_citation = await self.get_quote("^NSEI")
        sensex, bse_citation = await self.get_quote("^BSESN")
        overview = {
            "nifty50": {"value": nifty["ltp"], "change_pct": nifty["change_pct"]},
            "sensex": {"value": sensex["ltp"], "change_pct": sensex["change_pct"]},
        }
        citations = nse_citation + bse_citation
        return overview, citations

    async def get_price_history(
        self,
        ticker: str,
        days: int = 30,
        limit: int = 30,
        cursor: str | None = None,
    ) -> tuple[dict, list[dict]]:
        now = datetime.now(timezone.utc)
        symbol = ticker.upper().replace(".NS", "")
        seed = self._seed(symbol)
        total_days = max(1, min(days, 365))
        page_limit = max(1, min(limit, 100))
        start = int(cursor or "0")

        full_rows = []
        base = 100 + (seed % 240000) / 100.0
        for idx in range(total_days):
            day_seed = (seed + idx * 7919) % 1000003
            drift = ((day_seed % 2400) / 100.0) - 12.0
            close = round(max(base + drift, 1.0), 2)
            date_value = (now - timedelta(days=idx)).date().isoformat()
            full_rows.append(
                {
                    "date": date_value,
                    "open": round(max(close - ((day_seed % 400) / 100.0), 1.0), 2),
                    "high": round(close + ((day_seed % 500) / 100.0), 2),
                    "low": round(max(close - ((day_seed % 500) / 100.0), 1.0), 2),
                    "close": close,
                    "volume": 100000 + (day_seed % 2400000),
                }
            )
        rows = full_rows[start : start + page_limit]
        next_cursor = str(start + page_limit) if start + page_limit < len(full_rows) else None

        return (
            {"items": rows, "page_info": {"limit": page_limit, "next_cursor": next_cursor, "total_items": len(full_rows)}},
            [
                {
                    "source": "Deterministic OHLCV fallback",
                    "reference": symbol,
                    "as_of": now.isoformat(),
                }
            ],
        )

    async def get_top_movers(self) -> tuple[dict, list[dict]]:
        gainers = [{"ticker": "ADANIENT", "change_pct": 4.2}, {"ticker": "TATASTEEL", "change_pct": 3.7}]
        losers = [{"ticker": "BAJAJFINSV", "change_pct": -3.8}, {"ticker": "HINDALCO", "change_pct": -3.1}]
        return (
            {"gainers": gainers, "losers": losers},
            [{"source": "NSE India / fallback mover set", "reference": "top_gainers_losers"}],
        )

