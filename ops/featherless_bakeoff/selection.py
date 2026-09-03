from __future__ import annotations

from collections import Counter
from typing import Any

import httpx
import pandas as pd

from clockcross.agent.adjudicator import AgentContext
from clockcross.domain import AgentDecision
from clockcross.research.featherless_bakeoff import (
    Action,
    EpisodeScore,
    consensus_action,
    effective_replacement_action,
    evaluate_policy,
    passes_promotion_gates,
    stable_action,
)

from featherless_bakeoff.config import MODELS, REPEATS, SELECTION_END
from featherless_bakeoff.provider import BudgetStop, FeatherlessResearchClient


def policy_return(action: Action, residual: float, forward_return: float) -> float:
    sign = 1 if residual > 0 else -1
    if action == "abstain":
        return 0.0
    direction = sign if action == "continuation" else -sign
    return float(direction) * forward_return


def serializable_decision(decision: AgentDecision) -> dict[str, Any]:
    return decision.model_dump(mode="json")


def run_selection(
    *,
    selection: pd.DataFrame,
    contexts: dict[Any, AgentContext],
    incumbents: dict[Any, AgentDecision],
    featherless: FeatherlessResearchClient,
) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    model_results: dict[str, Any] = {}
    eligible: list[dict[str, Any]] = []
    budget_stopped = False

    for model_index, model in enumerate(MODELS):
        try:
            detail = featherless.model_detail(model)
        except Exception as exc:
            model_results[model] = {
                "available": False,
                "reason": f"model_detail_error:{type(exc).__name__}",
            }
            continue
        if not featherless.model_available(detail):
            model_results[model] = {
                "available": False,
                "status": detail.get("status"),
                "available_on_current_plan": detail.get("available_on_current_plan"),
                "is_gated": detail.get("is_gated"),
                "availability": detail.get("availability"),
            }
            continue

        episodes: list[dict[str, Any]] = []
        replacement_scores: list[EpisodeScore] = []
        consensus_scores: list[EpisodeScore] = []
        rejected = False

        for _, row in selection.iterrows():
            session_date = row["session_date"]
            context = contexts[session_date]
            incumbent = incumbents[session_date]
            observations: list[dict[str, Any]] = []
            actions: list[Action] = []
            valid_count = 0
            try:
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
            except BudgetStop:
                budget_stopped = True
                rejected = True
                break
            except httpx.HTTPStatusError as exc:
                rejected = True
                observations.append(
                    {"error": f"http_status:{exc.response.status_code}", "valid": False}
                )
                break

            modal = stable_action(actions)
            stable = modal is not None and valid_count >= 4
            challenger: Action = modal if stable and modal is not None else "abstain"
            incumbent_action: Action = incumbent.action.value
            replacement = effective_replacement_action(
                challenger=challenger,
                incumbent=incumbent_action,
                incumbent_idiosyncratic=incumbent.idiosyncratic_news_detected,
            )
            consensus = consensus_action(incumbent_action, challenger)
            residual = float(row["residual"])
            forward = float(row["forward_60m_return"])
            incumbent_return = policy_return(incumbent_action, residual, forward)
            replacement_return = policy_return(replacement, residual, forward)
            consensus_return = policy_return(consensus, residual, forward)
            replacement_scores.append(
                EpisodeScore(
                    session_date,
                    incumbent_return,
                    replacement_return,
                    replacement != "abstain",
                    stable,
                )
            )
            consensus_scores.append(
                EpisodeScore(
                    session_date,
                    incumbent_return,
                    consensus_return,
                    consensus != "abstain",
                    stable,
                )
            )
            episodes.append(
                {
                    "session_date": session_date.isoformat(),
                    "vote_counts": dict(sorted(Counter(actions).items())),
                    "valid_count": valid_count,
                    "stable": stable,
                    "challenger_action": challenger,
                    "effective_replacement_action": replacement,
                    "consensus_action": consensus,
                    "incumbent_action": incumbent_action,
                    "incumbent_idiosyncratic_veto": incumbent.idiosyncratic_news_detected,
                    "observations": observations,
                }
            )

        if rejected or len(replacement_scores) != len(selection):
            model_results[model] = {
                "available": True,
                "request_rejected_or_budget_stopped": True,
                "detail": compact_detail(detail),
                "episodes": episodes,
            }
            if budget_stopped:
                break
            continue

        replacement_metrics = evaluate_policy(
            replacement_scores,
            selection_end=SELECTION_END,
            bootstrap_samples=20_000,
            seed=20260903 + model_index * 10 + 1,
        )
        consensus_metrics = evaluate_policy(
            consensus_scores,
            selection_end=SELECTION_END,
            bootstrap_samples=20_000,
            seed=20260903 + model_index * 10 + 2,
        )
        replacement_pass = passes_promotion_gates(replacement_metrics)
        consensus_pass = passes_promotion_gates(consensus_metrics)
        model_results[model] = {
            "available": True,
            "detail": compact_detail(detail),
            "replacement": {
                "metrics": replacement_metrics,
                "passes_selection_gates": replacement_pass,
            },
            "consensus_filter": {
                "metrics": consensus_metrics,
                "passes_selection_gates": consensus_pass,
            },
            "episodes": episodes,
        }
        if replacement_pass:
            eligible.append(
                {
                    "model": model,
                    "policy": "featherless_directional_replacement",
                    "metrics": replacement_metrics,
                    "detail": detail,
                }
            )
        if consensus_pass:
            eligible.append(
                {
                    "model": model,
                    "policy": "incumbent_featherless_consensus_filter",
                    "metrics": consensus_metrics,
                    "detail": detail,
                }
            )

    eligible.sort(
        key=lambda item: (
            float(item["metrics"]["mean_improvement"]),
            float(item["metrics"]["bootstrap_ci_low"]),
        ),
        reverse=True,
    )
    return model_results, eligible, budget_stopped


def compact_detail(detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": detail.get("status"),
        "available_on_current_plan": detail.get("available_on_current_plan"),
        "is_gated": detail.get("is_gated"),
        "availability": detail.get("availability"),
        "pricing": detail.get("pricing"),
        "concurrency_cost": detail.get("concurrency_cost"),
    }
