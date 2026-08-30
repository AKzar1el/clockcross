from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import numpy as np


@dataclass(frozen=True)
class ReturnSummary:
    count: int
    mean: float
    median: float
    hit_rate: float
    standard_error: float
    total: float
    worst: float
    best: float
    leave_one_out_max_mean_impact: float


def summarize_returns(values: np.ndarray) -> ReturnSummary:
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    if clean.size == 0:
        return ReturnSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    mean = float(clean.mean())
    if clean.size > 1:
        standard_error = float(clean.std(ddof=1) / sqrt(clean.size))
        impacts = [abs(mean - float(np.delete(clean, i).mean())) for i in range(clean.size)]
        max_impact = max(impacts)
    else:
        standard_error = 0.0
        max_impact = abs(mean)

    return ReturnSummary(
        count=int(clean.size),
        mean=mean,
        median=float(np.median(clean)),
        hit_rate=float(np.mean(clean > 0.0)),
        standard_error=standard_error,
        total=float(clean.sum()),
        worst=float(clean.min()),
        best=float(clean.max()),
        leave_one_out_max_mean_impact=float(max_impact),
    )
