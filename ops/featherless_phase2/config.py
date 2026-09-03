from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, time as wall_time
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"
SELECTION_START = date(2026, 3, 2)
SELECTION_END = date(2026, 8, 31)
HOLDOUT_DATES = (date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3))
RAW_RESIDUAL_GATE = 0.01
FROZEN_RESEARCH_MEAN = 0.002745696957097104
EXPECTED_SELECTION_SIGNALS = 38
REPEATS = 5
MAX_SPEND_USD = 8.0
PRIOR_TESTED_POLICY_SLOTS = 8
PREDECLARED_CURRENT_POLICY_SLOTS = 17
TOTAL_SELECTION_TRIALS = PRIOR_TESTED_POLICY_SLOTS + PREDECLARED_CURRENT_POLICY_SLOTS
CONTRACT_CONTEXTS = 3
CONTRACT_REPEATS = 3
CONTRACT_P95_LIMIT_SECONDS = 12.0
CONTRACT_MAX_LIMIT_SECONDS = 20.0
WHITE_ALPHA = 0.05
PBO_MAX = 0.20
DSR_MIN = 0.95

PHASE2_MODELS = (
    "Qwen/Qwen3.8-Flash-Next",
    "moonshotai/Kimi-K3",
    "deepseek-ai/DeepSeek-V4-Pro",
    "MiniMaxAI/MiniMax-M3",
    "openai/gpt-oss-120b",
    "google/gemma-4-31B-it",
    "SUFE-AIFLM-Lab/Fin-R1",
    "NousResearch/DeepHermes-Financial-Fundamentals-Prediction-Specialist-Atropos",
)
PRIOR_CORRECTION_MODEL = "zai-org/GLM-5.3"
ALL_RESEARCH_MODELS = PHASE2_MODELS + (PRIOR_CORRECTION_MODEL,)
FRONTIER_ENSEMBLE = (
    "Qwen/Qwen3.8-Flash-Next",
    "moonshotai/Kimi-K3",
    "deepseek-ai/DeepSeek-V4-Pro",
    "MiniMaxAI/MiniMax-M3",
    "google/gemma-4-31B-it",
)
DIRECTIONAL_NEWS_BOUNDARY = (
    "Directional research only. Historical raw news is intentionally excluded because "
    "it cannot faithfully reproduce the live MCP payload. Do not infer company-specific "
    "news from outside this supplied context."
)
PROTOCOL_PATH = Path("artifacts/research/featherless-phase2-protocol-2026-09-04.json")
EXPECTED_PROTOCOL_SHA256 = "3bddffbb005ba6752243f50ffde0a8a3f216482689c4c4cd59a5b0ba1f82ae9f"


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"required environment variable is missing: {name}")
    return value


def utc_at(day: date, hour: int, minute: int) -> datetime:
    return datetime.combine(day, wall_time(hour, minute), tzinfo=ET).astimezone(UTC)


def verify_frozen_protocol() -> str:
    raw = PROTOCOL_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_PROTOCOL_SHA256:
        raise RuntimeError(
            "Phase-2 protocol hash mismatch; refusing credentialed research execution"
        )
    return digest
