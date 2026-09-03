from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from clockcross.agent.adjudicator import Adjudicator, AgentContext
from clockcross.domain import AgentDecision
from clockcross.research.featherless_bakeoff import BudgetLedger

from featherless_bakeoff.config import (
    DIRECTIONAL_NEWS_BOUNDARY,
    HOLDOUT_DATES,
    MAX_SPEND_USD,
    SELECTION_END,
    SELECTION_START,
    UTC,
    require_env,
)
from featherless_bakeoff.data import AlpacaHistoricalNews, build_context, build_market_frame
from featherless_bakeoff.holdout import run_holdout
from featherless_bakeoff.provider import FeatherlessResearchClient
from featherless_bakeoff.selection import run_selection, serializable_decision

FALLBACK = (
    "Cloudflare Llama authoritative production adjudicator -> Featherless GLM "
    "independent shadow/model-risk observer -> deterministic agreement/disagreement "
    "audit -> zero Featherless execution authority."
)


def run(output_path: Path) -> dict[str, Any]:
    alpaca_key = require_env("ALPACA_API_KEY")
    alpaca_secret = require_env("ALPACA_SECRET_KEY")
    featherless_key = require_env("FEATHERLESS_API_KEY")
    llm_key = require_env("LLM_API_KEY")
    llm_base_url = os.environ.get(
        "LLM_BASE_URL", "https://clockcross-ai-gateway.tomi-seregi99.workers.dev/v1"
    )
    llm_model = os.environ.get("LLM_MODEL", "clockcross-cloudflare-llama-3.3-70b")

    frame, complete, selection, anchors = build_market_frame(alpaca_key, alpaca_secret)
    news = AlpacaHistoricalNews(alpaca_key, alpaca_secret)
    incumbent = Adjudicator(
        base_url=llm_base_url,
        api_key=llm_key,
        model=llm_model,
        timeout_seconds=30.0,
    )
    budget = BudgetLedger(MAX_SPEND_USD)
    featherless = FeatherlessResearchClient(featherless_key, budget)

    contexts: dict[Any, AgentContext] = {}
    incumbents: dict[Any, AgentDecision] = {}
    selection_records: list[dict[str, Any]] = []
    for _, row in selection.iterrows():
        session_date = row["session_date"]
        context = build_context(
            row, frame=frame, news_summary=DIRECTIONAL_NEWS_BOUNDARY
        )
        decision = incumbent.decide(context)
        contexts[session_date] = context
        incumbents[session_date] = decision
        selection_records.append(
            {
                "session_date": session_date.isoformat(),
                "residual": float(row["residual"]),
                "forward_60m_return": float(row["forward_60m_return"]),
                "news_boundary": "retrospective_raw_news_excluded_from_model_input",
                "incumbent": serializable_decision(decision),
            }
        )

    model_results, eligible, budget_stopped = run_selection(
        selection=selection,
        contexts=contexts,
        incumbents=incumbents,
        featherless=featherless,
    )
    holdout: dict[str, Any] = {
        "evaluated": False,
        "reason": "no selection candidate cleared all predeclared gates",
    }
    conclusion = "fallback_shadow_architecture"
    if eligible and not budget_stopped:
        holdout = run_holdout(
            winner=eligible[0],
            complete=complete,
            frame=frame,
            news=news,
            incumbent=incumbent,
            featherless=featherless,
        )
        if holdout["passes_no_collapse_gate"] is True:
            conclusion = "candidate_for_manual_inspection_no_auto_promotion"

    result = {
        "study": "clockcross_featherless_predeclared_bakeoff",
        "generated_at": datetime.now(UTC).isoformat(),
        "protocol_path": "artifacts/research/featherless-bakeoff-protocol-2026-09-03.json",
        "selection_window": [SELECTION_START.isoformat(), SELECTION_END.isoformat()],
        "holdout_dates": [value.isoformat() for value in HOLDOUT_DATES],
        "anchors": anchors,
        "featherless_plan": featherless.plan,
        "budget": {
            "hard_max_spend_usd": MAX_SPEND_USD,
            "actual_accounted_spend_usd": budget.spent_usd,
            "budget_stopped": budget_stopped,
        },
        "selection_incumbent_contexts": selection_records,
        "models": model_results,
        "eligible_candidates_before_holdout": [
            {"model": item["model"], "policy": item["policy"], "metrics": item["metrics"]}
            for item in eligible
        ],
        "holdout": holdout,
        "conclusion": conclusion,
        "fallback_architecture": FALLBACK,
        "limitations": [
            "Retrospective Alpaca REST news is excluded from model input because prior ClockCross research showed it did not faithfully reproduce the live MCP decision or accepted production-context aggregate; timestamp-capped REST news is holdout diagnostic metadata only.",
            "Directional 60-minute returns are diagnostics, not compounded account returns or exact option P&L.",
            "Arbitrary-past option snapshot BBO and Greeks are unavailable, so counterfactual option fills are not invented.",
            "The Sep 1 observed production spread P&L is reported separately and is not used to choose a Featherless model or policy.",
            "No order endpoint, paper-order client, or portfolio mutation endpoint is instantiated by this research harness.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n")
    return result
