from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from math import e, isfinite, log, sqrt
from statistics import NormalDist
from typing import Literal, Sequence

import numpy as np
from numpy.typing import NDArray

Action = Literal["continuation", "reversion", "abstain"]


@dataclass
class BudgetLedger:
    max_spend_usd: float
    spent_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.max_spend_usd <= 0.0:
            raise ValueError("max_spend_usd must be positive")

    def can_start(self, worst_case_cost_usd: float) -> bool:
        if worst_case_cost_usd < 0.0:
            raise ValueError("worst_case_cost_usd cannot be negative")
        return self.spent_usd + worst_case_cost_usd <= self.max_spend_usd + 1e-12

    def record_success(self, cost_usd: float) -> None:
        if cost_usd < 0.0:
            raise ValueError("cost_usd cannot be negative")
        if self.spent_usd + cost_usd > self.max_spend_usd + 1e-12:
            raise RuntimeError("request would exceed hard research budget")
        self.spent_usd += cost_usd


def stable_action(actions: Sequence[Action], *, minimum_votes: int = 4) -> Action | None:
    if len(actions) != 5:
        raise ValueError("stable_action requires exactly five observations")
    if minimum_votes < 1 or minimum_votes > len(actions):
        raise ValueError("invalid minimum_votes")
    action, votes = Counter(actions).most_common(1)[0]
    return action if votes >= minimum_votes else None


def consensus_action(incumbent: Action, challenger: Action) -> Action:
    if incumbent == challenger and incumbent != "abstain":
        return incumbent
    return "abstain"


def frontier_ensemble_rounds(
    votes_by_model: dict[str, Sequence[Action]],
    *,
    members: Sequence[str],
) -> list[Action]:
    if len(members) != 5:
        raise ValueError("frontier ensemble is frozen to five members")
    if any(member not in votes_by_model for member in members):
        raise ValueError("missing frozen ensemble member")
    if any(len(votes_by_model[member]) != 5 for member in members):
        raise ValueError("every ensemble member requires five observations")

    result: list[Action] = []
    for repeat in range(5):
        counts = Counter(votes_by_model[member][repeat] for member in members)
        action, votes = counts.most_common(1)[0]
        if votes >= 3 and action != "abstain":
            result.append(action)
        else:
            result.append("abstain")
    return result


def policy_return(action: Action, residual: float, forward_return: float) -> float:
    if residual == 0.0:
        raise ValueError("signal residual must be non-zero")
    if action == "abstain":
        return 0.0
    residual_sign = 1.0 if residual > 0.0 else -1.0
    direction = residual_sign if action == "continuation" else -residual_sign
    return direction * forward_return


def _moving_block_indices(
    n: int,
    *,
    samples: int,
    block_length: int,
    seed: int,
) -> NDArray[np.int64]:
    if n <= 0 or samples <= 0 or block_length <= 0:
        raise ValueError("invalid moving-block bootstrap dimensions")
    rng = np.random.default_rng(seed)
    blocks = (n + block_length - 1) // block_length
    starts = rng.integers(0, n, size=(samples, blocks), dtype=np.int64)
    offsets = np.arange(block_length, dtype=np.int64)
    indices = (starts[:, :, None] + offsets[None, None, :]) % n
    return indices.reshape(samples, -1)[:, :n]


def block_bootstrap_ci(
    values: Sequence[float],
    *,
    samples: int = 20_000,
    block_length: int = 3,
    seed: int = 20260904,
) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        raise ValueError("at least one value is required")
    if array.size == 1:
        value = float(array[0])
        return value, value
    indices = _moving_block_indices(
        array.size,
        samples=samples,
        block_length=min(block_length, array.size),
        seed=seed,
    )
    means = array[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def white_reality_check(
    differences: NDArray[np.float64],
    *,
    samples: int = 20_000,
    block_length: int = 3,
    seed: int = 20260904,
) -> dict[str, object]:
    matrix = np.asarray(differences, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("differences must be a non-empty episode-by-strategy matrix")
    observed_by_strategy = matrix.mean(axis=0)
    observed_max = float(observed_by_strategy.max())
    centered = matrix - observed_by_strategy[None, :]
    indices = _moving_block_indices(
        matrix.shape[0],
        samples=samples,
        block_length=min(block_length, matrix.shape[0]),
        seed=seed,
    )
    bootstrap_max = centered[indices].mean(axis=1).max(axis=1)
    adjusted = [
        (1.0 + float(np.count_nonzero(bootstrap_max >= observed))) / (samples + 1.0)
        for observed in observed_by_strategy
    ]
    return {
        "observed_best_mean_improvement": observed_max,
        "p_value": min(adjusted),
        "adjusted_p_values": adjusted,
    }


def probability_backtest_overfitting(
    strategy_returns: NDArray[np.float64],
    *,
    blocks: int = 6,
) -> dict[str, float | int]:
    matrix = np.asarray(strategy_returns, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < blocks or matrix.shape[1] < 2:
        return {"pbo": 1.0, "splits": 0, "median_logit": float("-inf")}
    if blocks < 4 or blocks % 2 != 0:
        raise ValueError("blocks must be an even integer >= 4")

    episode_blocks = [np.asarray(chunk, dtype=int) for chunk in np.array_split(np.arange(matrix.shape[0]), blocks)]
    half = blocks // 2
    logits: list[float] = []
    for selected_blocks in combinations(range(blocks), half):
        selected = set(selected_blocks)
        in_sample = np.concatenate([episode_blocks[idx] for idx in sorted(selected)])
        out_sample = np.concatenate(
            [episode_blocks[idx] for idx in range(blocks) if idx not in selected]
        )
        is_scores = matrix[in_sample].mean(axis=0)
        chosen = int(np.argmax(is_scores))
        oos_scores = matrix[out_sample].mean(axis=0)
        order = np.argsort(oos_scores, kind="stable")
        rank_position = int(np.flatnonzero(order == chosen)[0])
        relative_rank = (rank_position + 1.0) / (matrix.shape[1] + 1.0)
        logits.append(log(relative_rank / (1.0 - relative_rank)))

    values = np.asarray(logits, dtype=float)
    return {
        "pbo": float(np.mean(values <= 0.0)),
        "splits": int(values.size),
        "median_logit": float(np.median(values)),
    }


def _sample_skew_kurtosis(values: NDArray[np.float64]) -> tuple[float, float]:
    mean = float(values.mean())
    std = float(values.std(ddof=1))
    if not isfinite(std) or std <= np.finfo(float).eps:
        return 0.0, 3.0
    standardized = (values - mean) / std
    skew = float(np.mean(standardized**3))
    kurtosis = float(np.mean(standardized**4))
    return skew, kurtosis


def deflated_sharpe_probability(
    returns: Sequence[float],
    *,
    trials: int,
) -> dict[str, float | int]:
    values = np.asarray(returns, dtype=float)
    if values.size < 3 or trials < 1:
        return {"probability": 0.0, "sharpe": 0.0, "benchmark_sharpe": float("inf"), "trials": trials}
    std = float(values.std(ddof=1))
    if not isfinite(std) or std <= np.finfo(float).eps:
        probability = 1.0 if float(values.mean()) > 0.0 else 0.0
        return {
            "probability": probability,
            "sharpe": float("inf") if probability == 1.0 else 0.0,
            "benchmark_sharpe": 0.0,
            "trials": trials,
        }

    sharpe = float(values.mean()) / std
    normal = NormalDist()
    euler_gamma = 0.5772156649015329
    trial_count = max(trials, 2)
    expected_max_z = (
        (1.0 - euler_gamma) * normal.inv_cdf(1.0 - 1.0 / trial_count)
        + euler_gamma * normal.inv_cdf(1.0 - 1.0 / (trial_count * e))
    )
    benchmark_sharpe = expected_max_z / sqrt(values.size - 1.0)
    skew, kurtosis = _sample_skew_kurtosis(values)
    variance_term = (
        1.0
        - skew * sharpe
        + ((kurtosis - 1.0) / 4.0) * sharpe * sharpe
    )
    if variance_term <= 0.0 or not isfinite(variance_term):
        probability = 0.0
    else:
        z_score = (
            (sharpe - benchmark_sharpe)
            * sqrt(values.size - 1.0)
            / sqrt(variance_term)
        )
        probability = normal.cdf(z_score)
    return {
        "probability": float(probability),
        "sharpe": sharpe,
        "benchmark_sharpe": float(benchmark_sharpe),
        "trials": trials,
    }


@dataclass(frozen=True)
class CandidateEpisode:
    session_date: date
    incumbent_return: float
    candidate_return: float
    traded: bool
    stable: bool
    valid: bool
    latency_seconds: float


def candidate_metrics(
    rows: Sequence[CandidateEpisode],
    *,
    trial_count: int,
    bootstrap_seed: int,
) -> dict[str, object]:
    if not rows:
        raise ValueError("candidate requires at least one episode")
    incumbent = np.asarray([row.incumbent_return for row in rows], dtype=float)
    candidate = np.asarray([row.candidate_return for row in rows], dtype=float)
    differences = candidate - incumbent
    ci_low, ci_high = block_bootstrap_ci(differences, seed=bootstrap_seed)

    if differences.size == 1:
        leave_episode = float(differences[0])
    else:
        leave_episode = min(
            float(np.delete(differences, idx).mean()) for idx in range(differences.size)
        )

    months = sorted({(row.session_date.year, row.session_date.month) for row in rows})
    month_values: list[float] = []
    for year, month in months:
        kept = [
            diff
            for row, diff in zip(rows, differences, strict=True)
            if (row.session_date.year, row.session_date.month) != (year, month)
        ]
        if kept:
            month_values.append(float(np.mean(np.asarray(kept, dtype=float))))
    leave_month = min(month_values) if month_values else float(differences.mean())

    midpoint = max(1, len(rows) // 2)
    first_half = float(differences[:midpoint].mean())
    second_half = float(differences[midpoint:].mean()) if midpoint < len(rows) else first_half

    traded = [row.candidate_return for row in rows if row.traded]
    hit_rate = (
        sum(value > 0.0 for value in traded) / len(traded)
        if traded
        else 0.0
    )
    latencies = np.asarray([row.latency_seconds for row in rows], dtype=float)
    dsr = deflated_sharpe_probability(candidate, trials=trial_count)
    return {
        "episode_count": len(rows),
        "trade_count": len(traded),
        "trade_hit_rate": hit_rate,
        "incumbent_mean_return": float(incumbent.mean()),
        "candidate_mean_return": float(candidate.mean()),
        "candidate_median_return": float(np.median(candidate)),
        "mean_improvement": float(differences.mean()),
        "block_bootstrap_ci_low": ci_low,
        "block_bootstrap_ci_high": ci_high,
        "leave_one_episode_out_min_mean_improvement": leave_episode,
        "leave_one_month_out_min_mean_improvement": leave_month,
        "chronological_first_half_improvement": first_half,
        "chronological_second_half_improvement": second_half,
        "all_actions_stable": all(row.stable for row in rows),
        "all_schema_valid": all(row.valid for row in rows),
        "latency_p95_seconds": float(np.quantile(latencies, 0.95)),
        "latency_max_seconds": float(latencies.max()),
        "deflated_sharpe": dsr,
    }


def passes_base_promotion_gates(metrics: dict[str, object]) -> bool:
    positive_keys = (
        "mean_improvement",
        "block_bootstrap_ci_low",
        "leave_one_episode_out_min_mean_improvement",
        "leave_one_month_out_min_mean_improvement",
        "chronological_first_half_improvement",
        "chronological_second_half_improvement",
    )
    for key in positive_keys:
        value = metrics.get(key)
        if not isinstance(value, (int, float)) or float(value) <= 0.0:
            return False
    if metrics.get("all_actions_stable") is not True:
        return False
    if metrics.get("all_schema_valid") is not True:
        return False
    latency_p95 = metrics.get("latency_p95_seconds")
    latency_max = metrics.get("latency_max_seconds")
    if not isinstance(latency_p95, (int, float)) or float(latency_p95) > 12.0:
        return False
    if not isinstance(latency_max, (int, float)) or float(latency_max) > 20.0:
        return False
    dsr = metrics.get("deflated_sharpe")
    if not isinstance(dsr, dict) or float(dsr.get("probability", 0.0)) < 0.95:
        return False
    return True
