from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AuthContext(BaseModel):
    sub: str
    tier: str
    scopes: set[str]
    exp: int
    aud: str


class Holding(BaseModel):
    ticker: str
    quantity: float
    avg_buy_price: float
    sector: str


class Alert(BaseModel):
    alert_id: str
    level: str
    category: str
    message: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    citations: list[dict]


class RiskScore(BaseModel):
    score: int
    breakdown: dict[str, int]
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ToolResponse(BaseModel):
    data: dict
    citations: list[dict]
    disclaimer: str = (
        "This output is for informational purposes only and does not constitute financial advice."
    )
