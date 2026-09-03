from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from clockcross.research.featherless_phase2 import (
    BudgetLedger,
    CandidateEpisode,
    candidate_metrics,
    deflated_sharpe_probability,
    frontier_ensemble_rounds,
    passes_base_promotion_gates,
    probability_backtest_overfitting,
    stable_action,
    white_reality_check,
)


def test_stable_action_requires_four_of_five() -> None:
    assert stable_action(["continuation"] * 4 + ["reversion"]) == "continuation"
    assert stable_action(["continuation"] * 3 + ["reversion"] * 2) is None


def test_fixed_frontier_ensemble_requires_five_members_and_majority() -> None:
    members = ("a", "b", "c", "d", "e")
    votes = {
        "a": ["continuation"] * 5,
        "b": ["continuation"] * 5,
        "c": ["continuation"] * 5,
        "d": ["reversion"] * 5,
        "e": ["abstain"] * 5,
    }
    rounds = frontier_ensemble_rounds(votes, members=members)
    assert rounds == ["continuation"] * 5
    assert stable_action(rounds) == "continuation"


def test_budget_never_allows_request_past_hard_ceiling() -> None:
    budget = BudgetLedger(0.10)
    assert budget.can_start(0.07)
    budget.record_success(0.07)
    assert not budget.can_start(0.04)


def test_reality_check_adjusts_for_search_universe() -> None:
    differences = np.column_stack(
        [
            np.full(38, 0.010),
            np.full(38, -0.002),
            np.tile([0.001, -0.001], 19),
        ]
    )
    result = white_reality_check(differences, samples=2000, seed=7)
    adjusted = result["adjusted_p_values"]
    assert isinstance(adjusted, list)
    assert float(adjusted[0]) < 0.01
    assert float(result["p_value"]) < 0.01


def test_cscv_pbo_is_low_when_same_strategy_dominates_all_splits() -> None:
    returns = np.column_stack(
        [
            np.full(36, 0.02),
            np.full(36, -0.01),
            np.tile([0.002, -0.002], 18),
        ]
    )
    result = probability_backtest_overfitting(returns, blocks=6)
    assert result["splits"] == 20
    assert result["pbo"] == 0.0


def test_deflated_sharpe_penalizes_trial_count() -> None:
    values = [0.01, 0.02, 0.015, 0.018, 0.011, 0.021] * 7
    low_trials = deflated_sharpe_probability(values, trials=2)
    high_trials = deflated_sharpe_probability(values, trials=25)
    assert float(high_trials["probability"]) <= float(low_trials["probability"])


def test_candidate_gate_requires_robust_stable_positive_improvement() -> None:
    start = date(2026, 3, 2)
    rows = [
        CandidateEpisode(
            session_date=start + timedelta(days=index * 5),
            incumbent_return=0.001,
            candidate_return=0.011 + (index % 3) * 0.001,
            traded=True,
            stable=True,
            valid=True,
            latency_seconds=2.0 + (index % 4) * 0.1,
        )
        for index in range(38)
    ]
    metrics = candidate_metrics(rows, trial_count=25, bootstrap_seed=11)
    assert passes_base_promotion_gates(metrics)


def test_frozen_protocol_has_exact_search_budget_and_models() -> None:
    path = Path("artifacts/research/featherless-phase2-protocol-2026-09-04.json")
    protocol = json.loads(path.read_text())
    assert protocol["budget"]["hard_additional_featherless_spend_usd"] == 8.0
    assert len(protocol["phase2_models"]) == 8
    assert protocol["untouched_holdout"]["loaded_only_after_all_selection_gates"] is True
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    config = Path("ops/featherless_phase2/config.py").read_text()
    assert digest in config


def test_phase2_harness_is_read_only_with_respect_to_trading() -> None:
    paths = [Path("ops/featherless-phase2.py"), *Path("ops/featherless_phase2").glob("*.py")]
    source = "\n".join(path.read_text() for path in paths).lower()
    forbidden = (
        "tradingclient",
        "submit_order",
        "cancel_order_by_id",
        "close_position",
        "paper-order",
    )
    assert not any(token in source for token in forbidden)
