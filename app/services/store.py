from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from app.models.domain import Alert, Holding, RiskScore


class JsonStore:
    def __init__(self, db_path: str = "data_store.json") -> None:
        self._path = Path(db_path)
        self._lock = Lock()
        if not self._path.exists():
            self._path.write_text(json.dumps({"portfolios": {}, "alerts": {}, "risk_scores": {}}))

    def _read(self) -> dict:
        with self._lock:
            return json.loads(self._path.read_text())

    def _write(self, payload: dict) -> None:
        with self._lock:
            self._path.write_text(json.dumps(payload, indent=2))

    def get_holdings(self, user_id: str) -> list[Holding]:
        payload = self._read()
        items = payload["portfolios"].get(user_id, [])
        return [Holding(**item) for item in items]

    def upsert_holding(self, user_id: str, holding: Holding) -> list[Holding]:
        payload = self._read()
        items = payload["portfolios"].get(user_id, [])
        by_ticker = {item["ticker"]: item for item in items}
        by_ticker[holding.ticker] = holding.model_dump()
        payload["portfolios"][user_id] = list(by_ticker.values())
        self._write(payload)
        return [Holding(**item) for item in payload["portfolios"][user_id]]

    def remove_holding(self, user_id: str, ticker: str) -> list[Holding]:
        payload = self._read()
        items = payload["portfolios"].get(user_id, [])
        payload["portfolios"][user_id] = [item for item in items if item["ticker"].upper() != ticker.upper()]
        self._write(payload)
        return [Holding(**item) for item in payload["portfolios"][user_id]]

    def get_alerts(self, user_id: str) -> list[Alert]:
        payload = self._read()
        return [Alert(**item) for item in payload["alerts"].get(user_id, [])]

    def set_alerts(self, user_id: str, alerts: list[Alert]) -> None:
        payload = self._read()
        payload["alerts"][user_id] = [a.model_dump() for a in alerts]
        self._write(payload)

    def get_risk_score(self, user_id: str) -> RiskScore | None:
        payload = self._read()
        data = payload["risk_scores"].get(user_id)
        return RiskScore(**data) if data else None

    def set_risk_score(self, user_id: str, score: RiskScore) -> None:
        payload = self._read()
        payload["risk_scores"][user_id] = score.model_dump()
        self._write(payload)

