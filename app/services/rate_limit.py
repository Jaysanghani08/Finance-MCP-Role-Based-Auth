from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.contracts import TIER_ANALYST, TIER_FREE, TIER_PREMIUM
from app.core.errors import RateLimitExceededError


class RateLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[datetime]] = defaultdict(deque)
        self._limits = {
            TIER_FREE: settings.free_rate_limit_per_hour,
            TIER_PREMIUM: settings.premium_rate_limit_per_hour,
            TIER_ANALYST: settings.analyst_rate_limit_per_hour,
        }

    def check(self, user_id: str, tier: str) -> None:
        now = datetime.now(timezone.utc)
        key = (user_id, tier)
        window_start = now - timedelta(hours=1)
        queue = self._events[key]
        while queue and queue[0] < window_start:
            queue.popleft()

        limit = self._limits.get(tier, settings.free_rate_limit_per_hour)
        if len(queue) >= limit:
            retry_after = int((queue[0] + timedelta(hours=1) - now).total_seconds())
            raise RateLimitExceededError(max(retry_after, 1))

        queue.append(now)

