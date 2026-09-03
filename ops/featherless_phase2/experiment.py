from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from clockcross.agent.adjudicator import Adjudicator
from clockcross.research.featherless_phase2 import BudgetLedger

from featherless_phase2.config import (
    FRONTIER_ENSEMBLE,
    MAX_SPEND_USD,
    PHASE2_MODELS,
    PRIOR_CORRECTION_MODEL,
    UTC,
    require_env,
    verify_frozen_protocol,
)
from featherless_phase2.data import build_selection_frame
from featherless_phase2.holdout import evaluate_holdout
from featherless_phase2.provider import FeatherlessClient
from featherless_phase2.screen import run_contract_screen
from featherless_phase2.selection import (
    assemble_candidates,
    run_historical_selection,
    select_winner,
)


def _write(output: Path, result: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n")


def run(output: Path) -> dict[str, Any]:
    protocol_hash = verify_frozen_protocol()
    alpaca_key = require_env("ALPACA_API_KEY")
    alpaca_secret = require_env("ALPACA_SECRET_KEY")
    featherless_key = require_env("FEATHERLESS_API_KEY")
    llm_key = require_env("LLM_API_KEY")
    llm_base = os.environ.get(
        "LLM_BASE_URL",
        "https://clockcross-ai-gateway.tomi-seregi99.workers.dev/v1",
    )
    llm_model = os.environ.get("LLM_MODEL", "clockcross-cloudflare-llama-3.3-70b")

    budget = BudgetLedger(MAX_SPEND_USD)
    client = FeatherlessClient(featherless_key, budget)
    incumbent = Adjudicator(
        base_url=llm_base,
        api_key=llm_key,
        model=llm_model,
        timeout_seconds=30.0,
    )

    contract, details, contract_budget_stopped = run_contract_screen(client)
    result: dict[str, Any] = {
        "study": "clockcross_featherless_phase2_predeclared_search",
        "generated_at": datetime.now(UTC).isoformat(),
        "protocol_sha256": protocol_hash,
        "phase2_models": list(PHASE2_MODELS),
        "prior_correction_model": PRIOR_CORRECTION_MODEL,
        "frontier_ensemble": list(FRONTIER_ENSEMBLE),
        "budget": {
            "hard_additional_max_usd": MAX_SPEND_USD,
            "accounted_spend_usd": budget.spent_usd,
            "stopped": contract_budget_stopped,
        },
        "contract_screen": contract,
        "selection": {"evaluated": False},
        "holdout": {"evaluated": False, "reason": "selection_not_completed"},
        "conclusion": "fallback_existing_production_policy",
    }
    if contract_budget_stopped:
        _write(output, result)
        return result

    frame, selection = build_selection_frame(alpaca_key, alpaca_secret)
    (
        model_results,
        episode_votes,
        incumbent_decisions,
        incumbent_returns,
        selection_budget_stopped,
    ) = run_historical_selection(
        selection=selection,
        frame=frame,
        incumbent=incumbent,
        client=client,
        contract=contract,
        details=details,
    )
    candidates, names, strategy_returns, differences = assemble_candidates(
        selection=selection,
        model_results=model_results,
        episode_votes=episode_votes,
        incumbent_decisions=incumbent_decisions,
        incumbent_returns=incumbent_returns,
    )
    winner, search_corrections = select_winner(
        candidates=candidates,
        strategy_returns=strategy_returns,
        differences=differences,
    )

    serializable_candidates = []
    for candidate in candidates:
        clean = {
            key: value
            for key, value in candidate.items()
            if key not in {"returns", "differences"}
        }
        serializable_candidates.append(clean)

    result["budget"] = {
        "hard_additional_max_usd": MAX_SPEND_USD,
        "accounted_spend_usd": budget.spent_usd,
        "stopped": selection_budget_stopped,
    }
    result["selection"] = {
        "evaluated": True,
        "signal_count": len(selection),
        "candidate_names": names,
        "candidates": serializable_candidates,
        "search_corrections": search_corrections,
        "winner_before_holdout": None
        if winner is None
        else {
            "name": winner["name"],
            "model": winner["model"],
            "policy": winner["policy"],
            "metrics": winner["metrics"],
            "white_adjusted_p_value": winner["white_adjusted_p_value"],
        },
        "model_execution": {
            model: {
                key: value
                for key, value in model_result.items()
                if key not in {"direct_rows", "consensus_rows"}
            }
            for model, model_result in model_results.items()
        },
        "episode_votes": {
            model: {
                session_date.isoformat(): {
                    "actions": record["actions"],
                    "valid_count": record["valid_count"],
                    "all_valid": record["all_valid"],
                    "stable": record["stable"],
                    "modal_action": record["modal_action"],
                    "latency_max_seconds": record["latency_max_seconds"],
                }
                for session_date, record in per_date.items()
            }
            for model, per_date in episode_votes.items()
        },
    }

    if winner is None or selection_budget_stopped:
        result["holdout"] = {
            "evaluated": False,
            "reason": (
                "budget_stopped_before_selection_complete"
                if selection_budget_stopped
                else "no candidate cleared every predeclared selection gate"
            ),
        }
    else:
        holdout = evaluate_holdout(
            winner=winner,
            alpaca_key=alpaca_key,
            alpaca_secret=alpaca_secret,
            incumbent=incumbent,
            client=client,
            details=details,
        )
        result["holdout"] = holdout
        if holdout["passes_no_collapse_gate"] is True:
            result["conclusion"] = "candidate_requires_monetization_and_production_soak"

    result["budget"]["accounted_spend_usd"] = budget.spent_usd
    result["limitations"] = [
        "Historical raw Alpaca REST news is excluded from model input because prior ClockCross research showed it does not faithfully reproduce the live MCP news context.",
        "The primary selection target is paired 60-minute underlying policy return, not invented historical option BBO/Greeks or exact options P&L.",
        "A selection winner is not production-ready until a separate honest monetization replay and provider/runtime soak also pass.",
        "No trading mutation client is instantiated by this research harness.",
        "The Phase-2 search family, trial count, ensemble membership, statistical thresholds, budget, and holdout rule are frozen by the protocol hash before credentialed calls begin.",
    ]
    _write(output, result)
    return result
