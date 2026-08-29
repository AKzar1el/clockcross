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
    thesis: Literal["continuation", "reversion"]
    normalization: Literal["raw", "zscore"]
    threshold: float
    horizon: Literal["forward_30m_return", "forward_60m_return"]
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
    normalizations: tuple[str, ...] = ("raw", "zscore")
    theses: tuple[str, ...] = ("continuation", "reversion")
    horizons: tuple[str, ...] = ("forward_30m_return", "forward_60m_return")
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
