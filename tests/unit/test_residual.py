import numpy as np
import pytest

from clockcross.research.residual import rolling_beta


def test_rolling_beta_recovers_known_linear_relationship() -> None:
    x = np.array([0.01, -0.02, 0.03, 0.00, 0.02])
    y = 1.5 * x
    assert rolling_beta(x, y) == pytest.approx(1.5)


def test_rolling_beta_returns_none_when_crypto_has_zero_variance() -> None:
    x = np.array([0.01, 0.01, 0.01])
    y = np.array([0.02, -0.01, 0.03])
    assert rolling_beta(x, y) is None
