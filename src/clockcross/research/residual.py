from __future__ import annotations

import numpy as np


def rolling_beta(crypto_returns: np.ndarray, equity_returns: np.ndarray) -> float | None:
    """Return the OLS slope (with intercept) of equity returns on crypto returns.

    The intercept itself is not used in the residual baseline. Returning ``None``
    for zero-variance crypto windows prevents unstable/infinite beta estimates.
    """

    x = np.asarray(crypto_returns, dtype=float)
    y = np.asarray(equity_returns, dtype=float)
    if x.shape != y.shape or x.ndim != 1 or x.size < 2:
        return None
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    if x.size < 2:
        return None
    centered_x = x - x.mean()
    denominator = float(np.dot(centered_x, centered_x))
    if denominator <= np.finfo(float).eps:
        return None
    centered_y = y - y.mean()
    return float(np.dot(centered_x, centered_y) / denominator)
