from datetime import date

import pandas as pd
import pytest

from clockcross.research import validation
from clockcross.research.episodes import build_episode_frame


def _bars(points: list[tuple[str, float]]) -> pd.DataFrame:
    index = pd.to_datetime([ts for ts, _ in points], utc=True)
    values = [value for _, value in points]
    return pd.DataFrame(
        {
            "open": values,
            "high": values,
            "low": values,
            "close": values,
            "volume": [100.0] * len(values),
        },
        index=index,
    )


def test_episode_builder_materializes_predeclared_exit_horizons_from_0955() -> None:
    equity = _bars(
        [
            ("2026-08-31T19:59:00Z", 100.0),
            ("2026-09-01T13:25:00Z", 101.0),
            ("2026-09-01T13:30:00Z", 101.0),
            ("2026-09-01T13:40:00Z", 102.0),
            ("2026-09-01T13:55:00Z", 100.0),
            ("2026-09-01T14:10:00Z", 101.0),
            ("2026-09-01T14:25:00Z", 102.0),
            ("2026-09-01T14:40:00Z", 103.0),
            ("2026-09-01T14:55:00Z", 104.0),
            ("2026-09-01T15:25:00Z", 105.0),
            ("2026-09-01T15:55:00Z", 106.0),
        ]
    )
    btc = _bars(
        [
            ("2026-08-31T19:59:00Z", 100_000.0),
            ("2026-09-01T13:25:00Z", 101_000.0),
        ]
    )

    row = build_episode_frame(
        btc,
        equity,
        sessions=[date(2026, 9, 1)],
        beta_lookback=1,
    ).iloc[0]

    assert row["forward_15m_return"] == pytest.approx(0.01)
    assert row["forward_30m_return"] == pytest.approx(0.02)
    assert row["forward_45m_return"] == pytest.approx(0.03)
    assert row["forward_60m_return"] == pytest.approx(0.04)
    assert row["forward_90m_return"] == pytest.approx(0.05)
    assert row["forward_120m_return"] == pytest.approx(0.06)
    assert row["training_count"] == 0


def _study_frame(*, outlier: bool = False) -> pd.DataFrame:
    sessions = [
        date(2025, 1, 2),
        date(2025, 2, 3),
        date(2025, 3, 3),
        date(2026, 1, 2),
        date(2026, 2, 2),
        date(2026, 3, 2),
    ]
    residuals = [0.02, -0.02, 0.03, -0.03, 0.025, -0.025]
    signed_60 = [0.01] * 6
    signed_30 = [0.02] * 6
    if outlier:
        signed_30 = [0.005, 0.005, 0.005, 0.005, 0.005, 0.10]

    def raw_returns(signed: list[float]) -> list[float]:
        return [value if residual > 0 else -value for residual, value in zip(residuals, signed)]

    payload = {
        "session_date": sessions,
        "residual": residuals,
        "training_count": [40] * 6,
        "forward_15m_return": raw_returns([0.008] * 6),
        "forward_30m_return": raw_returns(signed_30),
        "forward_45m_return": raw_returns([0.009] * 6),
        "forward_60m_return": raw_returns(signed_60),
        "forward_90m_return": raw_returns([0.007] * 6),
        "forward_120m_return": raw_returns([0.006] * 6),
    }
    return pd.DataFrame(payload)


def _evaluate(frame: pd.DataFrame) -> dict[str, object]:
    evaluator = getattr(validation, "evaluate_frozen_horizon_sensitivity", None)
    assert callable(evaluator), "frozen horizon sensitivity evaluator must exist"
    return evaluator(frame, bootstrap_samples=2000, bootstrap_seed=7)


def test_horizon_study_promotes_only_broad_paired_improvement() -> None:
    result = _evaluate(_study_frame())

    assert result["baseline_minutes"] == 60
    assert result["episode_count"] == 6
    assert result["recommended_minutes"] == 30
    assert result["promoted"] is True
    thirty = result["horizons"]["30"]
    assert thirty["paired_mean_improvement"] == pytest.approx(0.01)
    assert thirty["bootstrap_ci_low"] > 0
    assert thirty["leave_one_out_min_mean_improvement"] > 0
    assert thirty["yearly_not_worse"] is True


def test_horizon_study_rejects_outlier_driven_mean_improvement() -> None:
    result = _evaluate(_study_frame(outlier=True))

    assert result["recommended_minutes"] == 60
    assert result["promoted"] is False
    thirty = result["horizons"]["30"]
    assert thirty["mean_signed_return"] > result["horizons"]["60"]["mean_signed_return"]
    assert thirty["eligible_for_promotion"] is False


def test_horizon_study_uses_one_common_complete_episode_sample() -> None:
    frame = _study_frame()
    frame.loc[0, "forward_120m_return"] = None

    result = _evaluate(frame)

    assert result["episode_count"] == 5
    assert all(item["count"] == 5 for item in result["horizons"].values())


def test_horizon_study_requires_full_beta40_history() -> None:
    frame = _study_frame()
    frame.loc[0, "training_count"] = 39

    result = _evaluate(frame)

    assert result["episode_count"] == 5
    assert result["minimum_training_count"] == 40
