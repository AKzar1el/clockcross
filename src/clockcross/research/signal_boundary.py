from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from clockcross.research.metrics import summarize_returns

DEFAULT_THRESHOLDS = (0.008, 0.009, 0.010, 0.011, 0.012)
BASELINE_THRESHOLD = 0.010
LOCAL_LOWER_THRESHOLD = 0.009
LOCAL_UPPER_THRESHOLD = 0.011
MINIMUM_TRAINING_COUNT = 40

_REQUIRED_COLUMNS = {
    "session_date",
    "residual",
    "training_count",
    "forward_60m_return",
}


def _rounded(value: float) -> float:
    return round(float(value), 12)


def _threshold_key(value: float) -> str:
    return f"{value:.3f}"


def _validate_thresholds(thresholds: tuple[float, ...]) -> None:
    if not thresholds:
        raise ValueError("at least one threshold is required")
    if any(value <= 0 for value in thresholds):
        raise ValueError("thresholds must be positive")
    if tuple(sorted(set(thresholds))) != thresholds:
        raise ValueError("thresholds must be unique and strictly increasing")
    required = {
        BASELINE_THRESHOLD,
        LOCAL_LOWER_THRESHOLD,
        LOCAL_UPPER_THRESHOLD,
    }
    if not required.issubset(thresholds):
        raise ValueError("threshold grid must contain 0.9%, 1.0%, and 1.1%")


def _summary(values: np.ndarray) -> dict[str, float | int | None]:
    if values.size == 0:
        return {
            "count": 0,
            "mean_signed_return": None,
            "median_signed_return": None,
            "hit_rate": None,
        }
    summary = summarize_returns(values)
    return {
        "count": summary.count,
        "mean_signed_return": _rounded(summary.mean),
        "median_signed_return": _rounded(summary.median),
        "hit_rate": _rounded(summary.hit_rate),
    }


def _signed_returns(frame: pd.DataFrame) -> np.ndarray:
    residual = frame["residual"].to_numpy(dtype=float)
    forward = frame["forward_60m_return"].to_numpy(dtype=float)
    return np.asarray(np.sign(residual) * forward, dtype=float)


def _yearly_summary(frame: pd.DataFrame) -> dict[str, dict[str, float | int | None]]:
    if frame.empty:
        return {}
    years = pd.to_datetime(frame["session_date"]).dt.year
    result: dict[str, dict[str, float | int | None]] = {}
    for year in sorted(set(years.tolist())):
        subset = frame.loc[years == year]
        result[str(year)] = _summary(_signed_returns(subset))
    return result


def _shell_summary(
    frame: pd.DataFrame,
    *,
    lower: float,
    upper: float,
) -> dict[str, float | int | None]:
    magnitude = frame["residual"].astype(float).abs()
    subset = frame.loc[(magnitude >= lower) & (magnitude < upper)]
    return _summary(_signed_returns(subset))


def _require_float(
    payload: dict[str, object],
    key: str,
) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raise TypeError(f"{key} must be numeric")


def evaluate_threshold_boundary_robustness(
    frame: pd.DataFrame,
    *,
    thresholds: Iterable[float] = DEFAULT_THRESHOLDS,
    min_signal_count: int = 20,
    minimum_training_count: int = MINIMUM_TRAINING_COUNT,
) -> dict[str, object]:
    """Measure local sensitivity around the frozen 1% residual gate.

    This function deliberately does not rank or recommend alternative live
    thresholds. The 0.8% and 1.2% points are descriptive stress, while 0.9%
    and 1.1% are the predeclared local robustness neighbors around 1.0%.
    """
    if min_signal_count <= 0:
        raise ValueError("min_signal_count must be positive")
    if minimum_training_count <= 0:
        raise ValueError("minimum_training_count must be positive")

    threshold_tuple = tuple(float(value) for value in thresholds)
    _validate_thresholds(threshold_tuple)

    missing = _REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"missing signal-boundary columns: {sorted(missing)}")

    clean = frame.dropna(subset=sorted(_REQUIRED_COLUMNS)).copy()
    clean["session_date"] = pd.to_datetime(clean["session_date"])
    clean = clean.loc[
        clean["training_count"].astype(int) >= minimum_training_count
    ].sort_values("session_date")
    clean = clean.reset_index(drop=True)
    if clean.empty:
        raise ValueError("no full-history episodes available for signal-boundary study")

    magnitude = clean["residual"].astype(float).abs()
    baseline_mask = magnitude >= BASELINE_THRESHOLD
    baseline_dates = set(clean.loc[baseline_mask, "session_date"].tolist())

    threshold_results: dict[str, dict[str, object]] = {}
    for threshold in threshold_tuple:
        selected = clean.loc[magnitude >= threshold].copy()
        summary = _summary(_signed_returns(selected))
        selected_dates = set(selected["session_date"].tolist())
        baseline_overlap = len(selected_dates.intersection(baseline_dates))
        baseline_count = len(baseline_dates)
        count_value = summary["count"]
        if not isinstance(count_value, int):
            raise TypeError("threshold count must be an integer")
        selected_count = count_value
        threshold_results[_threshold_key(threshold)] = {
            **summary,
            "yearly": _yearly_summary(selected),
            "baseline_overlap_count": baseline_overlap,
            "baseline_overlap_rate": (
                _rounded(baseline_overlap / baseline_count) if baseline_count else None
            ),
            "baseline_share_of_selected": (
                _rounded(baseline_overlap / selected_count) if selected_count else None
            ),
        }

    baseline = threshold_results[_threshold_key(BASELINE_THRESHOLD)]
    lower = threshold_results[_threshold_key(LOCAL_LOWER_THRESHOLD)]
    upper = threshold_results[_threshold_key(LOCAL_UPPER_THRESHOLD)]
    baseline_mean = _require_float(baseline, "mean_signed_return")

    warnings: list[str] = []
    if baseline_mean is None or baseline_mean <= 0:
        warnings.append("baseline_nonpositive_mean")

    for label, payload in (("lower_neighbor", lower), ("upper_neighbor", upper)):
        count = payload["count"]
        if not isinstance(count, int):
            raise TypeError("threshold count must be an integer")
        mean = _require_float(payload, "mean_signed_return")
        median = _require_float(payload, "median_signed_return")
        hit_rate = _require_float(payload, "hit_rate")

        if count < min_signal_count:
            warnings.append(f"{label}_insufficient_signals")
        if mean is None or mean <= 0:
            warnings.append(f"{label}_nonpositive_mean")
        if median is None or median <= 0:
            warnings.append(f"{label}_nonpositive_median")
        if hit_rate is None or hit_rate < 0.50:
            warnings.append(f"{label}_hit_rate_below_50pct")
        if (
            baseline_mean is not None
            and baseline_mean > 0
            and (mean is None or mean < baseline_mean * 0.50)
        ):
            warnings.append(f"{label}_mean_below_half_baseline")

    boundary_shells = {
        "0.009-0.010": _shell_summary(
            clean,
            lower=LOCAL_LOWER_THRESHOLD,
            upper=BASELINE_THRESHOLD,
        ),
        "0.010-0.011": _shell_summary(
            clean,
            lower=BASELINE_THRESHOLD,
            upper=LOCAL_UPPER_THRESHOLD,
        ),
    }

    return {
        "policy": "coin-continuation-beta40-raw1pct-2026-08-29",
        "minimum_training_count": minimum_training_count,
        "eligible_episode_count": int(clean.shape[0]),
        "sample_start": clean.iloc[0]["session_date"].date().isoformat(),
        "sample_end": clean.iloc[-1]["session_date"].date().isoformat(),
        "tested_thresholds": list(threshold_tuple),
        "baseline_threshold": BASELINE_THRESHOLD,
        "local_lower_threshold": LOCAL_LOWER_THRESHOLD,
        "local_upper_threshold": LOCAL_UPPER_THRESHOLD,
        "min_signal_count": min_signal_count,
        "thresholds": threshold_results,
        "boundary_shells": boundary_shells,
        "local_boundary_robust": not warnings,
        "local_boundary_warnings": warnings,
        "live_threshold_change_recommended": False,
        "interpretation": (
            "Robustness diagnostic only; retrospective threshold ranking must not "
            "be used to retune the frozen live 1% gate."
        ),
    }
