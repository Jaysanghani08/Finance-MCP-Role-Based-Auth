from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import httpx

from app.core.config import settings


class NewsDataAdapter:
    @staticmethod
    def _seed(text: str) -> int:
        return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)

    async def get_company_news(
        self,
        ticker: str,
        days: int = 7,
        limit: int = 10,
        cursor: str | None = None,
    ) -> tuple[dict, list[dict]]:
        ticker = ticker.upper()
        page_limit = max(1, min(limit, 50))
        offset = max(0, int(cursor or "0"))
        citations: list[dict] = []
        if settings.news_api_key:
            try:
                url = "https://newsapi.org/v2/everything"
                page = int(offset / page_limit) + 1
                params = {
                    "q": f"{ticker} stock india",
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": page_limit,
                    "page": page,
                    "apiKey": settings.news_api_key,
                }
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    payload = resp.json()
                items = [
                    {
                        "title": item.get("title"),
                        "published_at": item.get("publishedAt"),
                        "url": item.get("url"),
                    }
                    for item in payload.get("articles", [])
                ]
                total_results = int(payload.get("totalResults", len(items)))
                next_cursor = str(offset + len(items)) if offset + len(items) < total_results else None
                citations.append(
                    {
                        "source": "NewsAPI",
                        "reference": f"query={ticker}",
                        "as_of": datetime.now(timezone.utc).isoformat(),
                    }
                )
                return (
                    {
                        "items": items,
                        "page_info": {
                            "limit": page_limit,
                            "next_cursor": next_cursor,
                            "total_items": total_results,
                            "days_window": days,
                        },
                    },
                    citations,
                )
            except Exception:
                pass

        seed = self._seed(f"{ticker}:{days}")
        total_results = 24
        synthetic = []
        for idx in range(total_results):
            day_offset = (seed + idx) % max(days, 1)
            published_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            synthetic.append(
                {
                    "title": f"{ticker}: Deterministic market digest {idx + 1}",
                    "published_at": published_at,
                    "url": f"https://example.com/mock-news/{ticker.lower()}/{idx + 1}?d={day_offset}",
                }
            )
        items = synthetic[offset : offset + page_limit]
        next_cursor = str(offset + page_limit) if offset + page_limit < len(synthetic) else None
        citations.append(
            {
                "source": "Deterministic news fallback",
                "reference": ticker,
                "as_of": datetime.now(timezone.utc).isoformat(),
            }
        )
        return (
            {
                "items": items,
                "page_info": {
                    "limit": page_limit,
                    "next_cursor": next_cursor,
                    "total_items": total_results,
                    "days_window": days,
                },
            },
            citations,
        )

    async def get_sentiment(self, ticker: str, window_days: int) -> tuple[dict, list[dict]]:
        seed = self._seed(f"{ticker.upper()}:{window_days}")
        score = round(((seed % 200) / 100.0) - 1.0, 2)
        mood = "positive" if score > 0.2 else "negative" if score < -0.2 else "neutral"
        return (
            {"ticker": ticker.upper(), "window_days": window_days, "score": score, "label": mood},
            [
                {
                    "source": "News sentiment aggregate",
                    "reference": f"{ticker.upper()}_{window_days}d",
                    "as_of": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )

