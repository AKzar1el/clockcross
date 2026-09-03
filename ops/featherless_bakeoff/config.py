from __future__ import annotations

import os
from datetime import date, datetime, time as wall_time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"
MODELS = (
    "meta-llama/Llama-3.3-70B-Instruct",
    "zai-org/GLM-5.3",
    "zai-org/GLM-5.3-Flash",
    "deepseek-ai/DeepSeek-V4-Flash-0731",
)
SELECTION_START = date(2026, 3, 2)
SELECTION_END = date(2026, 8, 31)
HOLDOUT_DATES = (date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3))
RECORDED_COMPANY_NEWS_VETO_DATES = {date(2026, 9, 3)}
FROZEN_RESEARCH_MEAN = 0.002745696957097104
DIRECTIONAL_NEWS_BOUNDARY = (
    "Directional bakeoff only. Retrospective raw news is intentionally excluded "
    "because it cannot faithfully reproduce the live MCP payload. Do not infer "
    "company-specific news from outside this context."
)
RAW_RESIDUAL_GATE = 0.01
REPEATS = 5
MAX_TOKENS = 220
MAX_SPEND_USD = 15.0
EXPECTED_SELECTION_SIGNALS = 38


def utc_at(day: date, hour: int, minute: int) -> datetime:
    return datetime.combine(day, wall_time(hour, minute), tzinfo=ET).astimezone(UTC)


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"required environment variable is missing: {name}")
    return value
