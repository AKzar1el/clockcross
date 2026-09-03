from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from clockcross.agent.adjudicator import Adjudicator, AgentContext
from clockcross.domain import AgentDecision
from clockcross.research.featherless_phase2 import (
    Action,
    CandidateEpisode,
    candidate_metrics,
    consensus_action,
    frontier_ensemble_rounds,
    passes_base_promotion_gates,
    policy_return,
    probability_backtest_overfitting,
    stable_action,
    white_reality_check,
)

from featherless_phase2.config import (
    ALL_RESEARCH_MODELS,
    DSR_MIN,
    FRONTIER_ENSEMBLE,
    PBO_MAX,
    PHASE2_MODELS,
    REPEATS,
    TOTAL_SELECTION_TRIALS,
    WHITE_ALPHA,
)
from featherless_phase2.data import build_context
from featherless_phase2.provider import BudgetStop, FeatherlessClient, compact_detail


def run_historical_selection(
    *,
    selection: pd.DataFrame,
    frame: pd.DataFrame,
    incumbent: Adjudicator,
    client: FeatherlessClient,
    contract: dict[str, Any],
    details: dict[str, dict[str, Any]],
) -> tuple[
    dict[str, Any],
    dict[str, dict[date, dict[str, Any]]],
    dict[date, AgentDecision],
    dict[date, float],
    bool,
]:
    contexts: dict[date, AgentContext] = {}
    incumbent_decisions: dict[date, AgentDecision] = {}
    incumbent_returns: dict[date, float] = {}
    for _, row in selection.iterrows():
        session_date = row["session_date"]
        context = build_context(row, frame=frame)
        decision = incumbent.decide(context)
        contexts[session_date] = context
        incumbent_decisions[session_date] = decision
        incumbent_returns[session_date] = policy_return(
            decision.action.value,
            float(row["residual"]),
            float(row["forward_60m_return"]),
        )

    model_results: dict[str, Any] = {}
    episode_votes: dict[str, dict[date, dict[str, Any]]] = {}
    budget_stopped = False
    for model in ALL_RESEARCH_MODELS:
        contract_result = contract.get(model, {})
        if contract_result.get("passed") is not True:
            model_results[model] = {
                "evaluated": False,
                "reason": "contract_screen_failed",
                "contract": contract_result,
            }
            continue
        detail = details[model]
        per_date: dict[date, dict[str, Any]] = {}
        model_failed: str | None = None
        try:
            for _, row in selection.iterrows():
                session_date = row["session_date"]
                actions: list[Action] = []
                records: list[dict[str, Any]] = []
                valid_count = 0
                latencies: list[float] = []
                for _ in range(REPEATS):
                    decision, valid, metadata = client.decide(
                        model=model,
                        detail=detail,
                        context=contexts[session_date],
                    )
                    actions.append(decision.action.value)
                    valid_count += int(valid)
                    latencies.append(float(metadata["latency_seconds"]))
                    records.append(
                        {
                            "decision": decision.model_dump(mode="json"),
                            "valid": valid,
                            "metadata": metadata,
                        }
                    )
                modal = stable_action(actions)
                per_date[session_date] = {
                    "actions": actions,
                    "valid_count": valid_count,
                    "all_valid": valid_count == REPEATS,
                    "stable": modal is not None and valid_count >= 4,
                    "modal_action": modal or "abstain",
                    "latency_max_seconds": max(latencies),
                    "observations": records,
                }
        except BudgetStop:
            budget_stopped = True
            model_failed = "budget_stop"
        except Exception as exc:
            model_failed = f"runtime:{type(exc).__name__}"

        if model_failed is not None or len(per_date) != len(selection):
            model_results[model] = {
                "evaluated": False,
                "reason": model_failed or "incomplete",
                "episodes_completed": len(per_date),
            }
            episode_votes[model] = per_date
            if budget_stopped:
                break
            continue

        episode_votes[model] = per_date
        direct_rows: list[CandidateEpisode] = []
        consensus_rows: list[CandidateEpisode] = []
        for _, row in selection.iterrows():
            session_date = row["session_date"]
            record = per_date[session_date]
            challenger: Action = record["modal_action"]
            incumbent_decision = incumbent_decisions[session_date]
            incumbent_action: Action = incumbent_decision.action.value
            direct_action: Action = (
                "abstain"
                if incumbent_decision.idiosyncratic_news_detected
                else challenger
            )
            consensus = consensus_action(incumbent_action, challenger)
            residual = float(row["residual"])
            forward = float(row["forward_60m_return"])
            incumbent_return = incumbent_returns[session_date]
            direct_rows.append(
                CandidateEpisode(
                    session_date=session_date,
                    incumbent_return=incumbent_return,
                    candidate_return=policy_return(direct_action, residual, forward),
                    traded=direct_action != "abstain",
                    stable=bool(record["stable"]),
                    valid=bool(record["all_valid"]),
                    latency_seconds=float(record["latency_max_seconds"]),
                )
            )
            consensus_rows.append(
                CandidateEpisode(
                    session_date=session_date,
                    incumbent_return=incumbent_return,
                    candidate_return=policy_return(consensus, residual, forward),
                    traded=consensus != "abstain",
                    stable=bool(record["stable"]),
                    valid=bool(record["all_valid"]),
                    latency_seconds=float(record["latency_max_seconds"]),
                )
            )

        model_results[model] = {
            "evaluated": True,
            "phase2_promotion_eligible": model in PHASE2_MODELS,
            "detail": compact_detail(detail),
            "direct_rows": direct_rows,
            "consensus_rows": consensus_rows,
        }
    return (
        model_results,
        episode_votes,
        incumbent_decisions,
        incumbent_returns,
        budget_stopped,
    )


def assemble_candidates(
    *,
    selection: pd.DataFrame,
    model_results: dict[str, Any],
    episode_votes: dict[str, dict[date, dict[str, Any]]],
    incumbent_decisions: dict[date, AgentDecision],
    incumbent_returns: dict[date, float],
) -> tuple[list[dict[str, Any]], list[str], np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    candidates: list[dict[str, Any]] = []
    names: list[str] = []
    returns_columns: list[list[float]] = []
    diff_columns: list[list[float]] = []

    for model in ALL_RESEARCH_MODELS:
        result = model_results.get(model, {})
        if result.get("evaluated") is not True:
            continue
        for family, row_key in (
            ("direct_replacement", "direct_rows"),
            ("incumbent_consensus", "consensus_rows"),
        ):
            rows = result[row_key]
            metrics = candidate_metrics(
                rows,
                trial_count=TOTAL_SELECTION_TRIALS,
                bootstrap_seed=20260904 + len(candidates) * 13,
            )
            name = f"{model}::{family}"
            raw_returns = [float(row.candidate_return) for row in rows]
            raw_diffs = [
                float(row.candidate_return - row.incumbent_return) for row in rows
            ]
            candidates.append(
                {
                    "name": name,
                    "model": model,
                    "policy": family,
                    "promotion_eligible": model in PHASE2_MODELS,
                    "metrics": metrics,
                    "passes_base_gates": passes_base_promotion_gates(metrics),
                    "returns": raw_returns,
                    "differences": raw_diffs,
                }
            )
            names.append(name)
            returns_columns.append(raw_returns)
            diff_columns.append(raw_diffs)

    ensemble_available = all(
        model_results.get(member, {}).get("evaluated") is True
        for member in FRONTIER_ENSEMBLE
    )
    if ensemble_available:
        ensemble_rows: list[CandidateEpisode] = []
        for _, row in selection.iterrows():
            session_date = row["session_date"]
            votes = {
                member: episode_votes[member][session_date]["actions"]
                for member in FRONTIER_ENSEMBLE
            }
            rounds = frontier_ensemble_rounds(votes, members=FRONTIER_ENSEMBLE)
            ensemble_modal = stable_action(rounds)
            stable = ensemble_modal is not None
            challenger: Action = ensemble_modal or "abstain"
            incumbent_decision = incumbent_decisions[session_date]
            action: Action = (
                "abstain"
                if incumbent_decision.idiosyncratic_news_detected
                else challenger
            )
            all_valid = all(
                episode_votes[member][session_date]["all_valid"]
                for member in FRONTIER_ENSEMBLE
            )
            parallel_latency_proxy = max(
                float(episode_votes[member][session_date]["latency_max_seconds"])
                for member in FRONTIER_ENSEMBLE
            )
            ensemble_rows.append(
                CandidateEpisode(
                    session_date=session_date,
                    incumbent_return=incumbent_returns[session_date],
                    candidate_return=policy_return(
                        action,
                        float(row["residual"]),
                        float(row["forward_60m_return"]),
                    ),
                    traded=action != "abstain",
                    stable=stable,
                    valid=all_valid,
                    latency_seconds=parallel_latency_proxy,
                )
            )
        metrics = candidate_metrics(
            ensemble_rows,
            trial_count=TOTAL_SELECTION_TRIALS,
            bootstrap_seed=20269999,
        )
        name = "frontier_5_model_majority::direct_replacement"
        raw_returns = [float(row.candidate_return) for row in ensemble_rows]
        raw_diffs = [
            float(row.candidate_return - row.incumbent_return) for row in ensemble_rows
        ]
        candidates.append(
            {
                "name": name,
                "model": "frontier_5_model_majority",
                "policy": "fixed_frontier_ensemble",
                "promotion_eligible": True,
                "metrics": metrics,
                "passes_base_gates": passes_base_promotion_gates(metrics),
                "returns": raw_returns,
                "differences": raw_diffs,
            }
        )
        names.append(name)
        returns_columns.append(raw_returns)
        diff_columns.append(raw_diffs)

    if not returns_columns:
        return (
            candidates,
            names,
            np.empty((len(selection), 0), dtype=float),
            np.empty((len(selection), 0), dtype=float),
        )
    return (
        candidates,
        names,
        np.asarray(returns_columns, dtype=float).T,
        np.asarray(diff_columns, dtype=float).T,
    )


def select_winner(
    *,
    candidates: list[dict[str, Any]],
    strategy_returns: np.ndarray[Any, Any],
    differences: np.ndarray[Any, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not candidates or strategy_returns.shape[1] < 2:
        return None, {
            "reality_check": {"p_value": 1.0},
            "pbo": {"pbo": 1.0, "splits": 0},
            "reason": "insufficient_valid_candidates",
        }
    reality = white_reality_check(differences, samples=20_000, seed=20260904)
    pbo = probability_backtest_overfitting(strategy_returns, blocks=6)
    adjusted = reality["adjusted_p_values"]
    assert isinstance(adjusted, list)
    for candidate, p_value in zip(candidates, adjusted, strict=True):
        candidate["white_adjusted_p_value"] = float(p_value)
        candidate["passes_multiple_testing"] = (
            float(p_value) < WHITE_ALPHA and float(pbo["pbo"]) <= PBO_MAX
        )
        candidate["passes_full_selection"] = (
            candidate["promotion_eligible"] is True
            and candidate["passes_base_gates"] is True
            and candidate["passes_multiple_testing"] is True
            and float(candidate["metrics"]["deflated_sharpe"]["probability"]) >= DSR_MIN
        )

    eligible = [candidate for candidate in candidates if candidate["passes_full_selection"]]
    eligible.sort(
        key=lambda item: (
            float(item["metrics"]["mean_improvement"]),
            -float(item["white_adjusted_p_value"]),
        ),
        reverse=True,
    )
    return eligible[0] if eligible else None, {"reality_check": reality, "pbo": pbo}
