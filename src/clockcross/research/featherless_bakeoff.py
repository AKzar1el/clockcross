from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Literal, Sequence

import numpy as np

Action = Literal["continuation", "reversion", "abstain"]


def action_direction(action: Action, residual: float) -> int | None:
    if residual == 0.0:
        raise ValueError("residual must be non-zero for a signal episode")
    sign = 1 if residual > 0.0 else -1
    if action == "continuation":
        return sign
    if action == "reversion":
        return -sign
    if action == "abstain":
        return None
    raise ValueError(f"unsupported action: {action}")


def stable_action(actions: Sequence[Action]) -> Action | None:
    if len(actions) != 5:
        raise ValueError("stable_action requires exactly five observations")
    counts = Counter(actions)
    action, votes = counts.most_common(1)[0]
    return action if votes >= 4 else None


def consensus_action(incumbent: Action, challenger: Action) -> Action:
    if incumbent == challenger and incumbent != "abstain":
        return incumbent
    return "abstain"


@dataclass
class BudgetLedger:
    max_spend_usd: float
    spent_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.max_spend_usd <= 0.0:
            raise ValueError("max_spend_usd must be positive")

    def record_success(
        self,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        prompt_price: float,
        completion_price: float,
        request_price: float = 0.0,
    ) -> float:
        if min(prompt_tokens, completion_tokens) < 0:
            raise ValueError("token counts cannot be negative")
        cost = (
            prompt_tokens * prompt_price
            + completion_tokens * completion_price
            + request_price
        )
        if self.spent_usd + cost > self.max_spend_usd + 1e-12:
            raise RuntimeError("recorded request would exceed hard research budget")
        self.spent_usd += cost
        return cost

    def can_start(self, *, worst_case_cost_usd: float) -> bool:
        if worst_case_cost_usd < 0.0:
            raise ValueError("worst_case_cost_usd cannot be negative")
        return self.spent_usd + worst_case_cost_usd <= self.max_spend_usd + 1e-12


@dataclass(frozen=True)
class EpisodeScore:
    session_date: date
    incumbent_return: float
    candidate_return: float
    candidate_traded: bool
    stable: bool


def _bootstrap_ci(values: np.ndarray, *, samples: int, seed: int) -> tuple[float, float]:
    if samples <= 0:
        raise ValueError("bootstrap_samples must be positive")
    if values.size == 0:
        raise ValueError("at least one paired episode is required")
    if values.size == 1:
        value = float(values[0])
        return value, value
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, values.size, size=(samples, values.size))
    means = values[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def evaluate_policy(
    rows: Sequence[EpisodeScore],
    *,
    selection_end: date | None = None,
    bootstrap_samples: int = 10_000,
    seed: int = 20260903,
) -> dict[str, object]:
    selected = [
        row for row in rows if selection_end is None or row.session_date <= selection_end
    ]
    if not selected:
        raise ValueError("no selection episodes")

    incumbent = np.asarray([row.incumbent_return for row in selected], dtype=float)
    candidate = np.asarray([row.candidate_return for row in selected], dtype=float)
    differences = candidate - incumbent
    ci_low, ci_high = _bootstrap_ci(differences, samples=bootstrap_samples, seed=seed)

    if differences.size == 1:
        leave_one_episode_min = float(differences[0])
    else:
        leave_one_episode_min = min(
            float(np.delete(differences, idx).mean()) for idx in range(differences.size)
        )

    months = sorted({(row.session_date.year, row.session_date.month) for row in selected})
    month_left_out: list[float] = []
    for year, month in months:
        kept = [
            diff
            for row, diff in zip(selected, differences, strict=True)
            if (row.session_date.year, row.session_date.month) != (year, month)
        ]
        if kept:
            month_left_out.append(float(np.mean(np.asarray(kept, dtype=float))))
    leave_one_month_min = (
        min(month_left_out) if month_left_out else float(differences.mean())
    )

    traded_returns = [
        row.candidate_return for row in selected if row.candidate_traded
    ]
    hit_rate = (
        sum(value > 0.0 for value in traded_returns) / len(traded_returns)
        if traded_returns
        else 0.0
    )

    return {
        "episode_count": len(selected),
        "candidate_trade_count": len(traded_returns),
        "candidate_hit_rate": hit_rate,
        "incumbent_mean_return": float(incumbent.mean()),
        "candidate_mean_return": float(candidate.mean()),
        "candidate_median_return": float(np.median(candidate)),
        "mean_improvement": float(differences.mean()),
        "bootstrap_ci_low": ci_low,
        "bootstrap_ci_high": ci_high,
        "leave_one_episode_out_min_mean_improvement": leave_one_episode_min,
        "leave_one_month_out_min_mean_improvement": leave_one_month_min,
        "all_actions_stable": all(row.stable for row in selected),
    }


def effective_replacement_action(
    *,
    challenger: Action,
    incumbent: Action,
    incumbent_idiosyncratic: bool,
) -> Action:
    if incumbent_idiosyncratic:
        return "abstain"
    return challenger


def passes_promotion_gates(metrics: dict[str, object]) -> bool:
    numeric_keys = (
        "mean_improvement",
        "bootstrap_ci_low",
        "leave_one_episode_out_min_mean_improvement",
        "leave_one_month_out_min_mean_improvement",
    )
    for key in numeric_keys:
        value = metrics.get(key)
        if not isinstance(value, (int, float)) or float(value) <= 0.0:
            return False
    return metrics.get("all_actions_stable") is True
