from datetime import date, timedelta

import numpy as np
import pandas as pd

from clockcross.research.validation import (
    EvaluationConfig,
    ResearchVerdict,
    evaluate_residual_strategy,
    expanding_folds,
)


def _dates(count: int) -> list[date]:
    start = date(2025, 1, 2)
    return [start + timedelta(days=i) for i in range(count)]


def _effect_frame(count: int, *, scale: float = 0.01) -> pd.DataFrame:
    residual = np.tile(np.array([-2.0, -1.2, 1.2, 2.0]), count // 4 + 1)[:count]
    # Reversion: positive residual -> negative forward return and vice versa.
    forward = -np.sign(residual) * scale
    return pd.DataFrame(
        {
            "session_date": _dates(count),
            "residual": residual,
            "forward_30m_return": forward,
            "forward_60m_return": forward * 1.2,
        }
    )


def test_expanding_folds_never_train_on_or_after_test_dates() -> None:
    folds = expanding_folds(_dates(120), min_train=60, test_size=20)
    assert len(folds) == 3
    for fold in folds:
        assert max(fold.train_dates) < min(fold.test_dates)


def test_persistent_effect_promotes_to_go() -> None:
    result = evaluate_residual_strategy(
        _effect_frame(160),
        EvaluationConfig(min_train=60, test_size=20, min_total_signals=20),
        control_frame=pd.DataFrame(
            {
                "session_date": _dates(160),
                "residual": np.tile([-2.0, 2.0], 80),
                "forward_30m_return": np.zeros(160),
                "forward_60m_return": np.zeros(160),
            }
        ),
    )
    assert result.verdict is ResearchVerdict.GO
    assert result.checks["multiple_positive_folds"] is True
    assert result.checks["control_not_equally_strong"] is True


def test_equal_control_effect_kills_crypto_specific_claim() -> None:
    primary = _effect_frame(160)
    result = evaluate_residual_strategy(
        primary,
        EvaluationConfig(min_train=60, test_size=20, min_total_signals=20),
        control_frame=primary.copy(),
    )
    assert result.verdict is ResearchVerdict.KILL
    assert result.checks["control_not_equally_strong"] is False


def test_raw_residual_thresholds_are_percentage_points_not_decimal_whole_units() -> None:
    from clockcross.research.validation import _candidate_grid

    candidates = _candidate_grid(EvaluationConfig())
    raw_thresholds = sorted({c.threshold for c in candidates if c.normalization == "raw"})
    z_thresholds = sorted({c.threshold for c in candidates if c.normalization == "zscore"})

    assert raw_thresholds == [0.005, 0.01, 0.015]
    assert z_thresholds == [0.5, 1.0, 1.5]


def test_validation_selects_beta_lookback_inside_each_chronological_fold() -> None:
    primary = {
        10: _effect_frame(160),
        20: pd.DataFrame(
            {
                "session_date": _dates(160),
                "residual": np.tile([-2.0, 2.0], 80),
                "forward_30m_return": np.zeros(160),
                "forward_60m_return": np.zeros(160),
            }
        ),
        40: pd.DataFrame(
            {
                "session_date": _dates(160),
                "residual": np.tile([-2.0, 2.0], 80),
                "forward_30m_return": np.zeros(160),
                "forward_60m_return": np.zeros(160),
            }
        ),
    }
    control = {lookback: frame.copy() for lookback, frame in primary.items()}
    for frame in control.values():
        frame["forward_30m_return"] = 0.0
        frame["forward_60m_return"] = 0.0

    result = evaluate_residual_strategy(
        primary,
        EvaluationConfig(min_train=60, test_size=20, min_total_signals=20),
        control_frame=control,
    )

    assert result.selected_configs
    assert {config.beta_lookback for config in result.selected_configs} == {10}
