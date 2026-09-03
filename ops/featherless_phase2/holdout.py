from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

from clockcross.agent.adjudicator import Adjudicator
from clockcross.research.featherless_phase2 import (
    Action,
    consensus_action,
    frontier_ensemble_rounds,
    policy_return,
    stable_action,
)

from featherless_phase2.config import (
    FRONTIER_ENSEMBLE,
    HOLDOUT_DATES,
    RAW_RESIDUAL_GATE,
    REPEATS,
)
from featherless_phase2.data import build_context, build_holdout_frame
from featherless_phase2.provider import FeatherlessClient


def evaluate_holdout(
    *,
    winner: dict[str, Any],
    alpaca_key: str,
    alpaca_secret: str,
    incumbent: Adjudicator,
    client: FeatherlessClient,
    details: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    frame, complete = build_holdout_frame(alpaca_key, alpaca_secret)
    policy = str(winner["policy"])
    model = str(winner["model"])
    models = FRONTIER_ENSEMBLE if policy == "fixed_frontier_ensemble" else (model,)

    records: list[dict[str, Any]] = []
    incumbent_returns: list[float] = []
    candidate_returns: list[float] = []
    all_stable = True
    for session_date in HOLDOUT_DATES:
        matching = complete.loc[complete["session_date"] == session_date]
        if matching.empty:
            raise RuntimeError(f"missing holdout session: {session_date}")
        row = matching.iloc[-1]
        residual = float(row["residual"])
        forward = float(row["forward_60m_return"])
        if abs(residual) < RAW_RESIDUAL_GATE:
            incumbent_returns.append(0.0)
            candidate_returns.append(0.0)
            records.append(
                {"session_date": session_date.isoformat(), "state": "threshold_abstain"}
            )
            continue

        context = build_context(row, frame=frame)
        incumbent_decision = incumbent.decide(context)
        recorded_sep3_veto = session_date == date(2026, 9, 3)
        incumbent_action: Action = incumbent_decision.action.value
        if recorded_sep3_veto:
            incumbent_action = "abstain"

        model_actions: dict[str, list[Action]] = {}
        model_valid: dict[str, bool] = {}
        for current_model in models:
            actions: list[Action] = []
            valid_all = True
            for _ in range(REPEATS):
                decision, valid, _metadata = client.decide(
                    model=current_model,
                    detail=details[current_model],
                    context=context,
                )
                actions.append(decision.action.value)
                valid_all = valid_all and valid
            model_actions[current_model] = actions
            model_valid[current_model] = valid_all

        if policy == "fixed_frontier_ensemble":
            rounds = frontier_ensemble_rounds(model_actions, members=FRONTIER_ENSEMBLE)
            modal = stable_action(rounds)
            stable = modal is not None and all(model_valid.values())
            challenger: Action = modal or "abstain"
        else:
            modal = stable_action(model_actions[model])
            stable = modal is not None and model_valid[model]
            challenger = modal or "abstain"
        all_stable = all_stable and stable

        if recorded_sep3_veto or incumbent_decision.idiosyncratic_news_detected:
            candidate_action: Action = "abstain"
        elif policy == "incumbent_consensus":
            candidate_action = consensus_action(incumbent_action, challenger)
        else:
            candidate_action = challenger

        incumbent_value = policy_return(incumbent_action, residual, forward)
        candidate_value = policy_return(candidate_action, residual, forward)
        incumbent_returns.append(incumbent_value)
        candidate_returns.append(candidate_value)
        records.append(
            {
                "session_date": session_date.isoformat(),
                "state": "signal",
                "residual": residual,
                "recorded_sep3_company_news_veto": recorded_sep3_veto,
                "incumbent_action": incumbent_action,
                "challenger_action": challenger,
                "candidate_action": candidate_action,
                "stable": stable,
            }
        )

    incumbent_mean = float(np.mean(incumbent_returns))
    candidate_mean = float(np.mean(candidate_returns))
    passed = all_stable and candidate_mean >= incumbent_mean - 1e-12
    return {
        "evaluated": True,
        "records": records,
        "incumbent_mean_return": incumbent_mean,
        "candidate_mean_return": candidate_mean,
        "all_actions_stable": all_stable,
        "passes_no_collapse_gate": passed,
    }
