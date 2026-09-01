from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import StrEnum
from typing import Literal, TypeAlias

import numpy as np
import pandas as pd

from clockcross.research.metrics import summarize_returns

Thesis = Literal["continuation", "reversion"]
Normalization = Literal["raw", "zscore"]
Horizon = Literal["forward_30m_return", "forward_60m_return"]
_FROZEN_HORIZON_MINUTES = (15, 30, 45, 60, 90, 120)
_FROZEN_HORIZON_BASELINE = 60
_FROZEN_SIGNAL_THRESHOLD = 0.01
_FROZEN_MIN_TRAINING_COUNT = 40


class ResearchVerdict(StrEnum):
    GO = "GO"
    MUTATE = "MUTATE"
    KILL = "KILL"


@dataclass(frozen=True)
class Fold:
    train_dates: list[date]
    test_dates: list[date]


@dataclass(frozen=True)
class CandidateConfig:
    thesis: Thesis
    normalization: Normalization
    threshold: float
    horizon: Horizon
    beta_lookback: int = 20


@dataclass(frozen=True)
class FoldResult:
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    signal_count: int
    mean_return: float
    median_return: float
    hit_rate: float
    selected_config: CandidateConfig


@dataclass(frozen=True)
class EvaluationConfig:
    min_train: int = 60
    test_size: int = 20
    min_total_signals: int = 20
    beta_lookbacks: tuple[int, ...] = (10, 20, 40)
    thresholds: tuple[float, ...] = (0.5, 1.0, 1.5)
    normalizations: tuple[Normalization, ...] = ("raw", "zscore")
    theses: tuple[Thesis, ...] = ("continuation", "reversion")
    horizons: tuple[Horizon, ...] = ("forward_30m_return", "forward_60m_return")
    friction_bps: tuple[int, ...] = (0, 25, 50, 100)


@dataclass(frozen=True)
class ValidationResult:
    verdict: ResearchVerdict
    checks: dict[str, bool]
    folds: list[FoldResult]
    selected_configs: list[CandidateConfig]
    total_signals: int
    mean_test_return: float
    control_mean_return: float | None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict.value,
            "checks": self.checks,
            "folds": [
                {
                    **asdict(fold),
                    "train_start": fold.train_start.isoformat(),
                    "train_end": fold.train_end.isoformat(),
                    "test_start": fold.test_start.isoformat(),
                    "test_end": fold.test_end.isoformat(),
                    "selected_config": asdict(fold.selected_config),
                }
                for fold in self.folds
            ],
            "selected_configs": [asdict(config) for config in self.selected_configs],
            "total_signals": self.total_signals,
            "mean_test_return": self.mean_test_return,
            "control_mean_return": self.control_mean_return,
            "metadata": self.metadata,
        }


FrameFamily: TypeAlias = pd.DataFrame | Mapping[int, pd.DataFrame]
_REQUIRED_COLUMNS = {"session_date", "residual", "forward_30m_return", "forward_60m_return"}


def expanding_folds(dates: list[date], *, min_train: int, test_size: int) -> list[Fold]:
    if min_train <= 1 or test_size <= 0:
        raise ValueError("min_train must exceed 1 and test_size must be positive")
    ordered = sorted(dict.fromkeys(dates))
    folds: list[Fold] = []
    train_end = min_train
    while train_end + test_size <= len(ordered):
        folds.append(
            Fold(
                train_dates=ordered[:train_end],
                test_dates=ordered[train_end : train_end + test_size],
            )
        )
        train_end += test_size
    return folds


def _clean_frame(frame: pd.DataFrame) -> pd.DataFrame:
    missing = _REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"missing validation columns: {sorted(missing)}")
    clean = frame.dropna(subset=list(_REQUIRED_COLUMNS)).copy()
    clean["session_date"] = pd.to_datetime(clean["session_date"]).dt.date
    return clean.sort_values("session_date").reset_index(drop=True)


def _normalize_frames(frame: FrameFamily) -> dict[int, pd.DataFrame]:
    if isinstance(frame, pd.DataFrame):
        return {20: _clean_frame(frame)}
    if not frame:
        raise ValueError("at least one beta-lookback frame is required")
    return {int(lookback): _clean_frame(value) for lookback, value in frame.items()}


def _common_dates(frames: Mapping[int, pd.DataFrame]) -> list[date]:
    date_sets = [set(frame["session_date"].tolist()) for frame in frames.values()]
    if not date_sets:
        return []
    return sorted(set.intersection(*date_sets))


def _score_series(
    train: pd.DataFrame,
    target: pd.DataFrame,
    config: CandidateConfig,
) -> pd.Series:
    train_residual = train["residual"].astype(float)
    target_residual = target["residual"].astype(float)
    if config.normalization == "zscore":
        mean = float(train_residual.mean())
        std = float(train_residual.std(ddof=1))
        if not np.isfinite(std) or std <= np.finfo(float).eps:
            return pd.Series(np.nan, index=target.index, dtype=float)
        scores = (target_residual - mean) / std
    else:
        scores = target_residual
    direction = np.sign(scores)
    if config.thesis == "reversion":
        direction = -direction
    forward = target[config.horizon].astype(float)
    signed = direction * forward
    return signed.where(scores.abs() >= config.threshold)


def _candidate_grid(
    config: EvaluationConfig,
    available_lookbacks: tuple[int, ...] | None = None,
) -> list[CandidateConfig]:
    lookbacks = available_lookbacks or config.beta_lookbacks
    candidates: list[CandidateConfig] = []
    for beta_lookback in lookbacks:
        for thesis in config.theses:
            for normalization in config.normalizations:
                for threshold_level in config.thresholds:
                    threshold = (
                        threshold_level / 100.0
                        if normalization == "raw"
                        else threshold_level
                    )
                    for horizon in config.horizons:
                        candidates.append(
                            CandidateConfig(
                                thesis=thesis,
                                normalization=normalization,
                                threshold=threshold,
                                horizon=horizon,
                                beta_lookback=beta_lookback,
                            )
                        )
    return candidates


def _select_config(
    frames: Mapping[int, pd.DataFrame],
    train_dates: list[date],
    config: EvaluationConfig,
) -> CandidateConfig:
    available = tuple(sorted(set(frames).intersection(config.beta_lookbacks)))
    if not available:
        available = tuple(sorted(frames))
    best: CandidateConfig | None = None
    best_key = (-np.inf, -np.inf, 0)
    for candidate in _candidate_grid(config, available):
        frame = frames[candidate.beta_lookback]
        train = frame[frame["session_date"].isin(train_dates)]
        signed = _score_series(train, train, candidate).dropna().to_numpy(dtype=float)
        if signed.size < 2:
            continue
        summary = summarize_returns(signed)
        key = (summary.median, summary.mean, summary.count)
        if key > best_key:
            best_key = key
            best = candidate
    if best is None:
        first_lookback = available[0]
        return CandidateConfig(
            "reversion",
            "raw",
            float(config.thresholds[0]) / 100.0,
            "forward_30m_return",
            first_lookback,
        )
    return best


def _evaluate_without_control(
    frame: FrameFamily,
    config: EvaluationConfig,
) -> tuple[list[FoldResult], np.ndarray]:
    frames = _normalize_frames(frame)
    dates = _common_dates(frames)
    folds = expanding_folds(dates, min_train=config.min_train, test_size=config.test_size)

    fold_results: list[FoldResult] = []
    all_test_returns: list[float] = []
    for fold in folds:
        selected = _select_config(frames, fold.train_dates, config)
        selected_frame = frames[selected.beta_lookback]
        train = selected_frame[selected_frame["session_date"].isin(fold.train_dates)]
        test = selected_frame[selected_frame["session_date"].isin(fold.test_dates)]
        signed = _score_series(train, test, selected).dropna().to_numpy(dtype=float)
        summary = summarize_returns(signed)
        all_test_returns.extend(signed.tolist())
        fold_results.append(
            FoldResult(
                train_start=min(fold.train_dates),
                train_end=max(fold.train_dates),
                test_start=min(fold.test_dates),
                test_end=max(fold.test_dates),
                signal_count=summary.count,
                mean_return=summary.mean,
                median_return=summary.median,
                hit_rate=summary.hit_rate,
                selected_config=selected,
            )
        )
    return fold_results, np.asarray(all_test_returns, dtype=float)


def evaluate_residual_strategy(
    frame: FrameFamily,
    config: EvaluationConfig,
    *,
    control_frame: FrameFamily | None = None,
) -> ValidationResult:
    folds, returns = _evaluate_without_control(frame, config)
    summary = summarize_returns(returns)

    control_mean: float | None = None
    if control_frame is not None:
        _, control_returns = _evaluate_without_control(control_frame, config)
        control_mean = summarize_returns(control_returns).mean

    positive_folds = sum(fold.mean_return > 0.0 for fold in folds)
    strongest_friction = max(config.friction_bps, default=0) / 10_000.0
    control_ok = control_mean is None or summary.mean <= 0.0 or control_mean < summary.mean * 0.75
    checks = {
        "multiple_positive_folds": positive_folds >= 2,
        "enough_episodes": summary.count >= config.min_total_signals,
        "positive_mean": summary.mean > 0.0,
        "friction_survives": summary.mean > strongest_friction,
        "not_single_episode_driven": (
            summary.count > 1
            and summary.leave_one_out_max_mean_impact <= max(abs(summary.mean), 0.001)
        ),
        "control_not_equally_strong": control_ok,
    }

    if not control_ok:
        verdict = ResearchVerdict.KILL
    elif all(checks.values()):
        verdict = ResearchVerdict.GO
    elif checks["multiple_positive_folds"] and checks["positive_mean"]:
        verdict = ResearchVerdict.MUTATE
    else:
        verdict = ResearchVerdict.KILL

    config_payload = json.dumps(asdict(config), sort_keys=True, default=list)
    config_hash = hashlib.sha256(config_payload.encode()).hexdigest()[:16]
    selected = [fold.selected_config for fold in folds]
    return ValidationResult(
        verdict=verdict,
        checks=checks,
        folds=folds,
        selected_configs=selected,
        total_signals=summary.count,
        mean_test_return=summary.mean,
        control_mean_return=control_mean,
        metadata={
            "config_hash": config_hash,
            "friction_bps": list(config.friction_bps),
            "fold_count": len(folds),
            "leave_one_out_max_mean_impact": summary.leave_one_out_max_mean_impact,
            "beta_lookbacks": list(config.beta_lookbacks),
        },
    )


def _paired_bootstrap_ci(
    differences: np.ndarray,
    *,
    samples: int,
    seed: int,
) -> tuple[float, float]:
    if samples <= 0:
        raise ValueError("bootstrap_samples must be positive")
    if differences.size == 0:
        raise ValueError("paired bootstrap requires at least one episode")
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, differences.size, size=(samples, differences.size))
    means = differences[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def evaluate_frozen_horizon_sensitivity(
    frame: pd.DataFrame,
    *,
    bootstrap_samples: int = 10_000,
    bootstrap_seed: int = 20260901,
) -> dict[str, object]:
    """Compare exit horizons while freezing the approved COIN continuation signal."""
    horizon_columns = {
        minutes: f"forward_{minutes}m_return" for minutes in _FROZEN_HORIZON_MINUTES
    }
    required = {
        "session_date",
        "residual",
        "training_count",
        *horizon_columns.values(),
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing horizon sensitivity columns: {sorted(missing)}")

    common = frame.dropna(subset=sorted(required)).copy()
    common["session_date"] = pd.to_datetime(common["session_date"])
    common = common.loc[
        common["training_count"].astype(int) >= _FROZEN_MIN_TRAINING_COUNT
    ]
    common = common.loc[common["residual"].astype(float).abs() >= _FROZEN_SIGNAL_THRESHOLD]
    common = common.sort_values("session_date").reset_index(drop=True)
    if common.empty:
        raise ValueError("no complete frozen-policy episodes for horizon sensitivity")

    residuals = common["residual"].to_numpy(dtype=float)
    direction = np.sign(residuals)
    signed_returns = {
        minutes: direction * common[column].to_numpy(dtype=float)
        for minutes, column in horizon_columns.items()
    }
    baseline = signed_returns[_FROZEN_HORIZON_BASELINE]
    baseline_summary = summarize_returns(baseline)
    years = common["session_date"].dt.year.to_numpy(dtype=int)

    horizons: dict[str, dict[str, object]] = {}
    eligible_scores: dict[int, float] = {}
    for minutes in _FROZEN_HORIZON_MINUTES:
        signed = signed_returns[minutes]
        summary = summarize_returns(signed)
        differences = signed - baseline
        paired_mean = float(differences.mean())
        ci_low, ci_high = _paired_bootstrap_ci(
            differences,
            samples=bootstrap_samples,
            seed=bootstrap_seed + minutes,
        )
        if differences.size > 1:
            leave_one_out_min = min(
                float(np.delete(differences, index).mean())
                for index in range(differences.size)
            )
        else:
            leave_one_out_min = paired_mean

        yearly_not_worse = all(
            float(signed[years == year].mean())
            >= float(baseline[years == year].mean()) - 1e-12
            for year in sorted(set(years.tolist()))
        )
        median_not_worse = summary.median >= baseline_summary.median - 1e-12
        hit_rate_not_worse = summary.hit_rate >= baseline_summary.hit_rate - 1e-12
        eligible = (
            minutes != _FROZEN_HORIZON_BASELINE
            and differences.size >= 5
            and paired_mean > 0.0
            and ci_low > 0.0
            and leave_one_out_min > 0.0
            and median_not_worse
            and hit_rate_not_worse
            and yearly_not_worse
        )
        if eligible:
            eligible_scores[minutes] = paired_mean

        horizons[str(minutes)] = {
            "count": summary.count,
            "mean_signed_return": summary.mean,
            "median_signed_return": summary.median,
            "hit_rate": summary.hit_rate,
            "paired_mean_improvement": paired_mean,
            "bootstrap_ci_low": ci_low,
            "bootstrap_ci_high": ci_high,
            "leave_one_out_min_mean_improvement": leave_one_out_min,
            "median_not_worse": median_not_worse,
            "hit_rate_not_worse": hit_rate_not_worse,
            "yearly_not_worse": yearly_not_worse,
            "eligible_for_promotion": eligible,
        }

    recommended = _FROZEN_HORIZON_BASELINE
    if eligible_scores:
        recommended = max(
            eligible_scores,
            key=lambda minutes: (
                eligible_scores[minutes],
                -abs(minutes - _FROZEN_HORIZON_BASELINE),
                -minutes,
            ),
        )

    return {
        "policy": "coin-continuation-beta40-raw1pct-2026-08-29",
        "threshold": _FROZEN_SIGNAL_THRESHOLD,
        "minimum_training_count": _FROZEN_MIN_TRAINING_COUNT,
        "baseline_minutes": _FROZEN_HORIZON_BASELINE,
        "tested_minutes": list(_FROZEN_HORIZON_MINUTES),
        "episode_count": int(common.shape[0]),
        "sample_start": common.iloc[0]["session_date"].date().isoformat(),
        "sample_end": common.iloc[-1]["session_date"].date().isoformat(),
        "recommended_minutes": recommended,
        "promoted": recommended != _FROZEN_HORIZON_BASELINE,
        "horizons": horizons,
    }
