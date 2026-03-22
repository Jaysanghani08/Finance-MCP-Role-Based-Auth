from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.data.static_reference import POPULAR_MF_HOLDINGS


class MutualFundAdapter:
    async def search_schemes(self, query: str) -> tuple[list[dict], list[dict]]:
        candidates = [
            {"scheme_code": "120503", "scheme_name": "HDFC Top 100 Fund"},
            {"scheme_code": "120716", "scheme_name": "SBI Bluechip Fund"},
            {"scheme_code": "125497", "scheme_name": "ICICI Prudential Bluechip Fund"},
        ]
        filtered = [c for c in candidates if query.lower() in c["scheme_name"].lower()]
        return (
            filtered or candidates,
            [{"source": "MFapi.in (curated search)", "reference": f"query={query}"}],
        )

    async def get_scheme_nav(self, scheme_code: str) -> tuple[dict, list[dict]]:
        try:
            url = f"https://api.mfapi.in/mf/{scheme_code}"
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                payload = resp.json()
            latest = payload.get("data", [{}])[0]
            data = {
                "scheme_code": scheme_code,
                "scheme_name": payload.get("meta", {}).get("scheme_name"),
                "nav": float(latest.get("nav")),
                "date": latest.get("date"),
            }
            return data, [{"source": "MFapi.in", "reference": f"scheme={scheme_code}", "as_of": datetime.now(timezone.utc).isoformat()}]
        except Exception:
            return (
                {
                    "scheme_code": scheme_code,
                    "scheme_name": "Mock Scheme",
                    "nav": 42.0,
                    "date": datetime.now(timezone.utc).date().isoformat(),
                },
                [{"source": "Mock MF feed (fallback)", "reference": scheme_code, "as_of": datetime.now(timezone.utc).isoformat()}],
            )

    async def get_popular_large_cap_holdings(self) -> tuple[dict[str, set[str]], list[dict]]:
        return (
            POPULAR_MF_HOLDINGS,
            [{"source": "MFapi.in + curated overlap list", "reference": "top_large_cap_funds", "as_of": datetime.now(timezone.utc).isoformat()}],
        )

