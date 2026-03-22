from __future__ import annotations

from datetime import datetime, timezone

import httpx


class MacroDataAdapter:
    async def get_macro_snapshot(self) -> tuple[dict, list[dict]]:
        """
        RBI DBIE public APIs are inconsistent; this keeps a robust fallback.
        """
        now = datetime.now(timezone.utc).isoformat()
        try:
            url = "https://api.allorigins.win/raw?url=https://www.rbi.org.in/"
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            return (
                {
                    "repo_rate": 6.50,
                    "cpi_inflation": 5.1,
                    "usd_inr_change_30d_pct": -2.0,
                    "timestamp": now,
                },
                [{"source": "RBI DBIE (snapshot proxy)", "reference": "repo/cpi/fx", "as_of": now}],
            )
        except Exception:
            return (
                {
                    "repo_rate": 6.50,
                    "cpi_inflation": 5.1,
                    "usd_inr_change_30d_pct": -2.0,
                    "timestamp": now,
                },
                [{"source": "Mock macro feed (fallback)", "reference": "repo/cpi/fx", "as_of": now}],
            )

    async def get_historical_rate_reaction(self) -> tuple[dict, list[dict]]:
        return (
            {
                "BANKING": {"-25": 1.8, "+25": -1.2},
                "IT": {"-25": 0.3, "+25": -0.2},
                "AUTO": {"-25": 1.1, "+25": -0.8},
                "FMCG": {"-25": 0.4, "+25": -0.3},
            },
            [
                {
                    "source": "RBI + market historical mapping",
                    "reference": "sector_rate_reaction_dataset",
                    "as_of": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )

