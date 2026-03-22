class AppError(Exception):
    """Base app error."""


class UnauthorizedError(AppError):
    """Raised when auth is missing or invalid."""


class ForbiddenError(AppError):
    """Raised when scope/tier does not permit operation."""


class RateLimitExceededError(AppError):
    """Raised when user exceeds rate limits."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


class UpstreamError(AppError):
    """Raised when upstream providers fail and no cache fallback exists."""
