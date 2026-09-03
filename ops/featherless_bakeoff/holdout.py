from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from clockcross.agent.adjudicator import Adjudicator
from clockcross.research.featherless_bakeoff import (
    Action,
    EpisodeScore,
    consensus_action,
    effective_replacement_action,
    stable_action,
)

from featherless_bakeoff.config import (
    HOLDOUT_DATES,
    RAW_RESIDUAL_GATE,
    RECORDED_COMPANY_NEWS_VETO_DATES,
    REPEATS,
)
from featherless_bakeoff.data import AlpacaHistoricalNews, build_context
from featherless_bakeoff.provider import FeatherlessResearchClient
from featherless_bakeoff.selection import policy_return, serializable_decision


def run_holdout(
    *,
    winner: dict[str, Any],
    complete: pd.DataFrame,
    frame: pd.DataFrame,
    news: AlpacaHistoricalNews,
    incumbent: Adjudicator,
    featherless: FeatherlessResearchClient,
) -> dict[str, Any]:
    model = str(winner["model"])
    policy = str(winner["policy"])
    detail = winner["detail"]
    rows: list[EpisodeScore] = []
    records: list[dict[str, Any]] = []

    for session_date in HOLDOUT_DATES:
        matching = complete.loc[complete["session_date"] == session_date]
        if matching.empty:
            raise RuntimeError(f"missing holdout market data for {session_date}")
        row = matching.iloc[-1]
        residual = float(row["residual"])
        forward = float(row["forward_60m_return"])
        if abs(residual) < RAW_RESIDUAL_GATE:
            rows.append(EpisodeScore(session_date, 0.0, 0.0, False, True))
            records.append(
                {
                    "session_date": session_date.isoformat(),
                    "state": "threshold_abstain",
                    "residual": residual,
                    "incumbent_return": 0.0,
                    "candidate_return": 0.0,
                }
            )
            continue

        news_summary, metadata = news.summary(session_date)
        context = build_context(row, frame=frame, news_summary=news_summary)
        incumbent_decision = incumbent.decide(context)
        observations: list[dict[str, Any]] = []
        actions: list[Action] = []
        valid_count = 0
        for _ in range(REPEATS):
            decision, valid, usage = featherless.decide(
                model=model,
                detail=detail,
                context=context,
            )
            actions.append(decision.action.value)
            valid_count += int(valid)
            observations.append(
                {
                    "decision": serializable_decision(decision),
                    "valid": valid,
                    "usage": usage,
                }
            )
        modal = stable_action(actions)
        stable = modal is not None and valid_count >= 4
        challenger: Action = modal if stable and modal is not None else "abstain"
        incumbent_action: Action = incumbent_decision.action.value
        recorded_veto = session_date in RECORDED_COMPANY_NEWS_VETO_DATES
        effective_veto = incumbent_decision.idiosyncratic_news_detected or recorded_veto
        if policy == "featherless_directional_replacement":
            candidate_action = effective_replacement_action(
                challenger=challenger,
                incumbent=incumbent_action,
                incumbent_idiosyncratic=effective_veto,
            )
        else:
            candidate_action = consensus_action(incumbent_action, challenger)
            if effective_veto:
                candidate_action = "abstain"
        if recorded_veto:
            incumbent_action = "abstain"

        incumbent_return = policy_return(incumbent_action, residual, forward)
        candidate_return = policy_return(candidate_action, residual, forward)
        rows.append(
            EpisodeScore(
                session_date,
                incumbent_return,
                candidate_return,
                candidate_action != "abstain",
                stable,
            )
        )
        records.append(
            {
                "session_date": session_date.isoformat(),
                "state": "signal",
                "residual": residual,
                "forward_60m_return": forward,
                "news": metadata,
                "incumbent": serializable_decision(incumbent_decision),
                "recorded_company_news_veto": recorded_veto,
                "challenger_vote_counts": dict(sorted(Counter(actions).items())),
                "challenger_valid_count": valid_count,
                "challenger_stable": stable,
                "challenger_action": challenger,
                "effective_incumbent_action": incumbent_action,
                "effective_candidate_action": candidate_action,
                "incumbent_return": incumbent_return,
                "candidate_return": candidate_return,
                "observations": observations,
            }
        )

    incumbent_mean = float(np.mean([row.incumbent_return for row in rows]))
    candidate_mean = float(np.mean([row.candidate_return for row in rows]))
    all_stable = all(row.stable for row in rows)
    passed = all_stable and candidate_mean >= incumbent_mean - 1e-12
    return {
        "evaluated": True,
        "winner_selected_without_holdout": {
            "model": model,
            "policy": policy,
            "selection_metrics": winner["metrics"],
        },
        "records": records,
        "incumbent_mean_policy_return": incumbent_mean,
        "candidate_mean_policy_return": candidate_mean,
        "all_actions_stable": all_stable,
        "passes_no_collapse_gate": passed,
        "observed_live_execution_diagnostic": {
            "2026-09-01": {
                "production_action": "reversion",
                "entry_debit_per_share": 5.23,
                "exit_value_per_share": 4.55,
                "gross_one_contract_pnl_usd": -68.0,
                "note": "Observed production spread outcome; not used for model selection or the primary directional promotion gate.",
            },
            "2026-09-02": {"production_action": "threshold_abstain"},
            "2026-09-03": {
                "production_action": "company_news_abstain",
                "note": "Recorded live veto is non-overridable; historical REST news is only a diagnostic reconstruction.",
            },
        },
    }
