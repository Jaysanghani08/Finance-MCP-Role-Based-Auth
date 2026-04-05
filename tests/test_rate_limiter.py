"""Tests for rate limiter."""

import pytest

from app.core.errors import RateLimitExceededError
from app.services.rate_limit import RateLimiter


class TestRateLimiter:
    def test_allows_under_limit(self):
        limiter = RateLimiter()
        for _ in range(30):
            limiter.check("user1", "free")

    def test_blocks_over_free_limit(self):
        limiter = RateLimiter()
        for _ in range(30):
            limiter.check("user1", "free")
        with pytest.raises(RateLimitExceededError) as exc_info:
            limiter.check("user1", "free")
        assert exc_info.value.retry_after_seconds > 0

    def test_premium_has_higher_limit(self):
        limiter = RateLimiter()
        for _ in range(150):
            limiter.check("user1", "premium")
        with pytest.raises(RateLimitExceededError):
            limiter.check("user1", "premium")

    def test_separate_users_have_separate_limits(self):
        limiter = RateLimiter()
        for _ in range(30):
            limiter.check("user1", "free")
        limiter.check("user2", "free")

    def test_retry_after_is_positive(self):
        limiter = RateLimiter()
        for _ in range(30):
            limiter.check("user1", "free")
        with pytest.raises(RateLimitExceededError) as exc_info:
            limiter.check("user1", "free")
        assert exc_info.value.retry_after_seconds >= 1
