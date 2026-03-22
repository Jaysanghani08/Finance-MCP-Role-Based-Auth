from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone


class UpstreamQuotaManager:
    """
    Tracks coarse upstream quotas so tool calls can avoid burning free-tier APIs.
    """

    def __init__(self) -> None:
        self._events: dict[str, deque[datetime]] = defaultdict(deque)
        self._limits = {
            "alpha_vantage_daily": (25, timedelta(days=1)),
            "newsapi_daily": (100, timedelta(days=1)),
            "finnhub_minute": (60, timedelta(minutes=1)),
        }

    def try_consume(self, provider_limit_key: str) -> bool:
        if provider_limit_key not in self._limits:
            return True
        limit, window = self._limits[provider_limit_key]
        now = datetime.now(timezone.utc)
        queue = self._events[provider_limit_key]
        cutoff = now - window
        while queue and queue[0] < cutoff:
            queue.popleft()
        if len(queue) >= limit:
            return False
        queue.append(now)
        return True

