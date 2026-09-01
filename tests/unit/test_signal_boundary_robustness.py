from datetime import date, timedelta

import pandas as pd

from clockcross.research import signal_boundary


BASE = date(2026, 1, 2)


def _frame(
    residuals: list[float],
    signed_returns: list[float],
    *,
    training_counts: list[int] | None = None,
) -> pd.DataFrame:
    if training_counts is None:
        training_counts = [40] * len(residuals)
    raw_returns = [
        value if residual > 0 else -value
        for residual, value in zip(residuals, signed_returns)
    ]
    return pd.DataFrame(
        {
            "session_date": [BASE + timedelta(days=index) for index in range(len(residuals))],
            "residual": residuals,
            "training_count": training_counts,
            "forward_60m_return": raw_returns,
        }
    )


def test_local_threshold_neighbors_can_pass_without_selecting_a_new_threshold() -> None:
    residuals = [
        0.0082,
        -0.0085,
        0.0092,
        -0.0095,
        0.0102,
        -0.0105,
        0.0112,
        -0.0115,
        0.0122,
        -0.0125,
    ]
    frame = _frame(residuals, [0.01] * len(residuals))

    result = signal_boundary.evaluate_threshold_boundary_robustness(
        frame,
        min_signal_count=2,
    )

    assert result["baseline_threshold"] == 0.01
    assert result["tested_thresholds"] == [0.008, 0.009, 0.01, 0.011, 0.012]
    assert result["local_lower_threshold"] == 0.009
    assert result["local_upper_threshold"] == 0.011
    assert result["local_boundary_robust"] is True
    assert result["live_threshold_change_recommended"] is False
    assert result["thresholds"]["0.010"]["mean_signed_return"] == 0.01


def test_lower_neighbor_exposes_knife_edge_when_added_shell_is_destructive() -> None:
    residuals = [
        0.0091,
        -0.0092,
        0.0093,
        -0.0094,
        0.0102,
        -0.0104,
        0.0115,
        -0.0120,
    ]
    signed_returns = [-0.08, -0.08, -0.08, -0.08, 0.02, 0.02, 0.02, 0.02]
    frame = _frame(residuals, signed_returns)

    result = signal_boundary.evaluate_threshold_boundary_robustness(
        frame,
        min_signal_count=2,
    )

    assert result["thresholds"]["0.010"]["mean_signed_return"] > 0
    assert result["thresholds"]["0.009"]["mean_signed_return"] < 0
    assert result["local_boundary_robust"] is False
    assert "lower_neighbor_nonpositive_mean" in result["local_boundary_warnings"]
    assert result["live_threshold_change_recommended"] is False


def test_full_beta40_training_depth_is_required() -> None:
    frame = _frame(
        [0.012, -0.012, 0.013],
        [0.01, 0.01, -0.50],
        training_counts=[40, 40, 39],
    )

    result = signal_boundary.evaluate_threshold_boundary_robustness(
        frame,
        min_signal_count=1,
    )

    assert result["eligible_episode_count"] == 2
    assert result["minimum_training_count"] == 40
    assert result["thresholds"]["0.012"]["count"] == 2
    assert result["thresholds"]["0.012"]["mean_signed_return"] == 0.01


def test_boundary_shells_are_reported_around_frozen_one_percent_gate() -> None:
    frame = _frame(
        [0.0092, -0.0098, 0.0102, -0.0108, 0.0115],
        [0.01, 0.02, 0.03, 0.04, 0.05],
    )

    result = signal_boundary.evaluate_threshold_boundary_robustness(
        frame,
        min_signal_count=1,
    )

    assert result["boundary_shells"]["0.009-0.010"]["count"] == 2
    assert result["boundary_shells"]["0.009-0.010"]["mean_signed_return"] == 0.015
    assert result["boundary_shells"]["0.010-0.011"]["count"] == 2
    assert result["boundary_shells"]["0.010-0.011"]["mean_signed_return"] == 0.035
