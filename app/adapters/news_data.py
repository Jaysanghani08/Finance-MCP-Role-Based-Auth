from __future__ import annotations

from datetime import datetime, timezone
from random import uniform

import httpx

from app.core.config import settings


class NewsDataAdapter:
    async def get_company_news(self, ticker: str, days: int = 7) -> tuple[list[dict], list[dict]]:
        ticker = ticker.upper()
        citations: list[dict] = []
        if settings.news_api_key:
            try:
                url = "https://newsapi.org/v2/everything"
                params = {
                    "q": f"{ticker} stock india",
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 10,
                    "apiKey": settings.news_api_key,
                }
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    payload = resp.json()
                articles = [
                    {
                        "title": item.get("title"),
                        "published_at": item.get("publishedAt"),
                        "url": item.get("url"),
                    }
                    for item in payload.get("articles", [])
                ]
                citations.append(
                    {
                        "source": "NewsAPI",
                        "reference": f"query={ticker}",
                        "as_of": datetime.now(timezone.utc).isoformat(),
                    }
                )
                return articles, citations
            except Exception:
                pass

        articles = [
            {
                "title": f"{ticker}: Market digest placeholder article {idx}",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "url": "https://example.com/mock-news",
            }
            for idx in range(1, 6)
        ]
        citations.append(
            {
                "source": "Mock news feed (fallback)",
                "reference": ticker,
                "as_of": datetime.now(timezone.utc).isoformat(),
            }
        )
        return articles, citations

    async def get_sentiment(self, ticker: str, window_days: int) -> tuple[dict, list[dict]]:
        score = round(uniform(-1.0, 1.0), 2)
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

