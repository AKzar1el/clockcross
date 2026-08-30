from datetime import date

import pandas as pd
import pytest

from clockcross.research.episodes import build_episode_frame


def _bars(points: list[tuple[str, float]]) -> pd.DataFrame:
    index = pd.to_datetime([ts for ts, _ in points], utc=True)
    closes = [value for _, value in points]
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [100.0] * len(points),
        },
        index=index,
    )


def test_feature_freeze_ignores_post_0925_premarket_jump() -> None:
    equity = _bars(
        [
            ("2026-08-28T19:59:00Z", 100.0),
            ("2026-08-31T13:25:00Z", 102.0),
            ("2026-08-31T13:26:00Z", 150.0),
            ("2026-08-31T13:30:00Z", 103.0),
            ("2026-08-31T13:40:00Z", 104.0),
            ("2026-08-31T14:10:00Z", 105.0),
            ("2026-08-31T14:40:00Z", 106.0),
        ]
    )
    btc = _bars(
        [
            ("2026-08-28T19:59:00Z", 100_000.0),
            ("2026-08-31T13:25:00Z", 102_000.0),
        ]
    )

    frame = build_episode_frame(
        btc,
        equity,
        sessions=[date(2026, 8, 31)],
        beta_lookback=1,
    )

    assert frame.iloc[0]["premarket_price"] == pytest.approx(102.0)
    assert frame.iloc[0]["equity_premarket_return"] == pytest.approx(0.02)


def test_current_session_is_not_used_to_fit_beta() -> None:
    sessions = [date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 31)]
    equity = _bars(
        [
            ("2026-08-26T19:59:00Z", 100.0),
            ("2026-08-27T13:25:00Z", 102.0),
            ("2026-08-27T13:30:00Z", 102.0),
            ("2026-08-27T13:40:00Z", 102.5),
            ("2026-08-27T14:10:00Z", 103.0),
            ("2026-08-27T14:40:00Z", 103.5),
            ("2026-08-27T19:59:00Z", 102.0),
            ("2026-08-28T13:25:00Z", 106.08),
            ("2026-08-28T13:30:00Z", 106.0),
            ("2026-08-28T13:40:00Z", 106.5),
            ("2026-08-28T14:10:00Z", 107.0),
            ("2026-08-28T14:40:00Z", 107.5),
            ("2026-08-28T19:59:00Z", 106.08),
            ("2026-08-31T13:25:00Z", 212.16),
            ("2026-08-31T13:30:00Z", 212.0),
            ("2026-08-31T13:40:00Z", 213.0),
            ("2026-08-31T14:10:00Z", 214.0),
            ("2026-08-31T14:40:00Z", 215.0),
        ]
    )
    btc = _bars(
        [
            ("2026-08-26T19:59:00Z", 100_000.0),
            ("2026-08-27T13:25:00Z", 101_000.0),
            ("2026-08-27T19:59:00Z", 101_000.0),
            ("2026-08-28T13:25:00Z", 103_020.0),
            ("2026-08-28T19:59:00Z", 103_020.0),
            ("2026-08-31T13:25:00Z", 104_050.2),
        ]
    )

    frame = build_episode_frame(btc, equity, sessions=sessions, beta_lookback=2)
    monday = frame.loc[frame["session_date"] == date(2026, 8, 31)].iloc[0]

    # Prior sessions encode ~2x equity premarket response to BTC; Monday's huge
    # equity move must not contaminate the fitted beta for Monday.
    assert monday["beta"] == pytest.approx(2.0, rel=0.1)
    assert monday["expected_return"] < 0.05


def test_forward_returns_start_at_delayed_sip_decision_time() -> None:
    equity = _bars(
        [
            ("2026-08-28T19:59:00Z", 100.0),
            ("2026-08-31T13:25:00Z", 101.0),
            ("2026-08-31T13:30:00Z", 100.0),
            ("2026-08-31T13:40:00Z", 102.0),
            ("2026-08-31T13:55:00Z", 104.0),
            ("2026-08-31T14:25:00Z", 106.0),
            ("2026-08-31T14:55:00Z", 108.0),
        ]
    )
    btc = _bars(
        [
            ("2026-08-28T19:59:00Z", 100_000.0),
            ("2026-08-31T13:25:00Z", 101_000.0),
        ]
    )

    frame = build_episode_frame(btc, equity, sessions=[date(2026, 8, 31)], beta_lookback=1)
    row = frame.iloc[0]

    assert row["open_10m_return"] == pytest.approx(0.02)
    assert row["forward_30m_return"] == pytest.approx(106.0 / 104.0 - 1.0)
    assert row["forward_60m_return"] == pytest.approx(108.0 / 104.0 - 1.0)


def test_intraday_targets_use_bar_opens_at_exact_boundaries_not_future_minute_closes() -> None:
    index = pd.to_datetime(
        [
            "2026-08-28T19:59:00Z",
            "2026-08-31T13:25:00Z",
            "2026-08-31T13:30:00Z",
            "2026-08-31T13:40:00Z",
            "2026-08-31T13:55:00Z",
            "2026-08-31T14:25:00Z",
            "2026-08-31T14:55:00Z",
        ],
        utc=True,
    )
    equity = pd.DataFrame(
        {
            "open": [100.0, 101.0, 100.0, 102.0, 104.0, 106.0, 108.0],
            "high": [100.0, 101.0, 101.0, 141.0, 151.0, 161.0, 171.0],
            "low": [100.0, 101.0, 99.0, 101.0, 103.0, 105.0, 107.0],
            "close": [100.0, 101.0, 101.0, 140.0, 150.0, 160.0, 170.0],
            "volume": [100.0] * 7,
        },
        index=index,
    )
    btc = _bars(
        [
            ("2026-08-28T19:59:00Z", 100_000.0),
            ("2026-08-31T13:25:00Z", 101_000.0),
        ]
    )

    row = build_episode_frame(
        btc,
        equity,
        sessions=[date(2026, 8, 31)],
        beta_lookback=1,
    ).iloc[0]

    assert row["open_10m_return"] == pytest.approx(102.0 / 100.0 - 1.0)
    assert row["forward_30m_return"] == pytest.approx(106.0 / 104.0 - 1.0)
    assert row["forward_60m_return"] == pytest.approx(108.0 / 104.0 - 1.0)


def test_prior_close_excludes_1600_after_hours_bar() -> None:
    equity = _bars(
        [
            ("2026-08-28T19:59:00Z", 100.0),  # 15:59 ET regular-session minute
            ("2026-08-28T20:00:00Z", 200.0),  # 16:00 ET after-hours minute
            ("2026-08-31T13:25:00Z", 102.0),
            ("2026-08-31T13:30:00Z", 102.0),
            ("2026-08-31T13:40:00Z", 103.0),
            ("2026-08-31T13:55:00Z", 103.0),
            ("2026-08-31T14:25:00Z", 104.0),
            ("2026-08-31T14:55:00Z", 105.0),
        ]
    )
    btc = _bars(
        [
            ("2026-08-28T19:59:00Z", 100_000.0),
            ("2026-08-31T13:25:00Z", 101_000.0),
        ]
    )

    row = build_episode_frame(
        btc,
        equity,
        sessions=[date(2026, 8, 31)],
        beta_lookback=1,
    ).iloc[0]

    assert row["prior_close"] == pytest.approx(100.0)
