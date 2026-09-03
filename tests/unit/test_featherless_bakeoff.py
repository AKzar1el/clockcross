from datetime import date

import pytest

from clockcross.research.featherless_bakeoff import (
    BudgetLedger,
    EpisodeScore,
    action_direction,
    consensus_action,
    evaluate_policy,
    stable_action,
)


def test_action_direction_follows_or_opposes_residual_sign() -> None:
    assert action_direction("continuation", -0.02) == -1
    assert action_direction("continuation", 0.02) == 1
    assert action_direction("reversion", -0.02) == 1
    assert action_direction("reversion", 0.02) == -1
    assert action_direction("abstain", 0.02) is None


def test_stable_action_requires_four_of_five_votes() -> None:
    assert stable_action(["reversion"] * 4 + ["continuation"]) == "reversion"
    assert stable_action(["reversion"] * 3 + ["continuation"] * 2) is None
    with pytest.raises(ValueError, match="exactly five"):
        stable_action(["reversion"] * 4)


def test_consensus_filter_trades_only_same_non_abstain_action() -> None:
    assert consensus_action("reversion", "reversion") == "reversion"
    assert consensus_action("continuation", "continuation") == "continuation"
    assert consensus_action("reversion", "continuation") == "abstain"
    assert consensus_action("reversion", "abstain") == "abstain"


def test_budget_uses_provider_pricing_and_refuses_worst_case_overrun() -> None:
    budget = BudgetLedger(max_spend_usd=15.0)
    budget.record_success(
        prompt_tokens=1_000,
        completion_tokens=100,
        prompt_price=0.000001,
        completion_price=0.000002,
    )
    assert budget.spent_usd == pytest.approx(0.0012)
    assert budget.can_start(worst_case_cost_usd=14.9987)
    assert not budget.can_start(worst_case_cost_usd=14.999)


def test_policy_evaluation_counts_abstain_as_zero_and_is_paired() -> None:
    rows = [
        EpisodeScore(
            date(2026, 7, 1),
            incumbent_return=0.01,
            candidate_return=0.02,
            candidate_traded=True,
            stable=True,
        ),
        EpisodeScore(
            date(2026, 7, 2),
            incumbent_return=-0.01,
            candidate_return=0.0,
            candidate_traded=False,
            stable=True,
        ),
        EpisodeScore(
            date(2026, 8, 1),
            incumbent_return=0.01,
            candidate_return=0.03,
            candidate_traded=True,
            stable=True,
        ),
    ]
    result = evaluate_policy(rows, bootstrap_samples=2000, seed=7)
    assert result["episode_count"] == 3
    assert result["candidate_trade_count"] == 2
    assert result["mean_improvement"] == pytest.approx(0.013333333333333334)
    assert result["all_actions_stable"] is True
    assert result["leave_one_episode_out_min_mean_improvement"] > 0
    assert result["leave_one_month_out_min_mean_improvement"] > 0


def test_holdout_dates_cannot_enter_selection_metrics() -> None:
    rows = [
        EpisodeScore(
            date(2026, 8, 31),
            incumbent_return=0.0,
            candidate_return=0.01,
            candidate_traded=True,
            stable=True,
        ),
        EpisodeScore(
            date(2026, 9, 1),
            incumbent_return=-1.0,
            candidate_return=1.0,
            candidate_traded=True,
            stable=True,
        ),
    ]
    result = evaluate_policy(
        rows,
        selection_end=date(2026, 8, 31),
        bootstrap_samples=1000,
        seed=3,
    )
    assert result["episode_count"] == 1
    assert result["mean_improvement"] == pytest.approx(0.01)


def test_replacement_cannot_override_incumbent_company_news_veto() -> None:
    from clockcross.research.featherless_bakeoff import effective_replacement_action

    assert effective_replacement_action(
        challenger="continuation",
        incumbent="abstain",
        incumbent_idiosyncratic=True,
    ) == "abstain"
    assert effective_replacement_action(
        challenger="reversion",
        incumbent="continuation",
        incumbent_idiosyncratic=False,
    ) == "reversion"


def test_promotion_requires_every_predeclared_gate() -> None:
    from clockcross.research.featherless_bakeoff import passes_promotion_gates

    good = {
        "mean_improvement": 0.01,
        "bootstrap_ci_low": 0.001,
        "leave_one_episode_out_min_mean_improvement": 0.002,
        "leave_one_month_out_min_mean_improvement": 0.003,
        "all_actions_stable": True,
    }
    assert passes_promotion_gates(good)
    for key in (
        "mean_improvement",
        "bootstrap_ci_low",
        "leave_one_episode_out_min_mean_improvement",
        "leave_one_month_out_min_mean_improvement",
    ):
        bad = dict(good)
        bad[key] = 0.0
        assert not passes_promotion_gates(bad)
    bad_stability = dict(good)
    bad_stability["all_actions_stable"] = False
    assert not passes_promotion_gates(bad_stability)
