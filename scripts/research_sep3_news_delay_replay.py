from __future__ import annotations

import importlib.util
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any

import requests

SCRIPT = Path(__file__).with_name("research_sep3_adaptive_regime.py")
spec = importlib.util.spec_from_file_location("sep3_adaptive", SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError("unable to load adaptive diagnostic")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def _delayed_news_payload(
    session: requests.Session,
    api_key: str,
    secret: str,
    day: Any,
) -> list[dict[str, Any]]:
    start = datetime.combine(day, time(0, 0), tzinfo=module.ET).astimezone(timezone.utc)
    # At the 09:55 ET decision, a Basic account's default news end is 15 minutes delayed.
    end = datetime.combine(day, time(9, 40), tzinfo=module.ET).astimezone(timezone.utc)
    response = session.get(
        "https://data.alpaca.markets/v1beta1/news",
        headers={"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret},
        params={
            "symbols": "COIN",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "sort": "desc",
            "limit": 10,
            "include_content": "false",
        },
        timeout=30,
    )
    response.raise_for_status()
    items = response.json().get("news", [])
    return [
        {
            "headline": str(item.get("headline", ""))[:300],
            "summary": str(item.get("summary", ""))[:400],
            "created_at": item.get("created_at"),
            "symbols": item.get("symbols", []),
        }
        for item in items
    ]


module._news_payload = _delayed_news_payload
module.main()
