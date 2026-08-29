from __future__ import annotations

from datetime import date, datetime, time
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from clockcross.research.residual import rolling_beta

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def _utc(session_date: date, wall_time: time) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(session_date, wall_time, tzinfo=ET).astimezone(UTC))


def _last_at_or_before(frame: pd.DataFrame, timestamp: pd.Timestamp) -> float | None:
    eligible = frame.loc[frame.index <= timestamp, "close"]
    if eligible.empty:
        return None
    return float(eligible.iloc[-1])


def _first_at_or_after(frame: pd.DataFrame, timestamp: pd.Timestamp) -> float | None:
    eligible = frame.loc[frame.index >= timestamp, "open"]
    if eligible.empty:
        return None
    return float(eligible.iloc[0])


def _prior_regular_close(equity: pd.DataFrame, session_date: date) -> tuple[pd.Timestamp, float] | None:
    current_midnight = pd.Timestamp(datetime.combine(session_date, time(0, 0), tzinfo=ET).astimezone(UTC))
    prior = equity.loc[equity.index < current_midnight]
    if prior.empty:
        return None
    prior_et = prior.tz_convert(ET)
    regular = prior[(prior_et.index.time >= time(9, 30)) & (prior_et.index.time <= time(16, 0))]
    if regular.empty:
        return None
    timestamp = regular.index[-1]
    return timestamp, float(regular.iloc[-1]["close"])


def _session_raw_row(
    btc: pd.DataFrame,
    equity: pd.DataFrame,
    session_date: date,
) -> dict[str, object] | None:
    prior = _prior_regular_close(equity, session_date)
    if prior is None:
        return None
    prior_ts, prior_close = prior

    freeze = _utc(session_date, time(9, 25))
    premarket_start = _utc(session_date, time(4, 0))
    premarket = equity[(equity.index >= premarket_start) & (equity.index <= freeze)]
    if premarket.empty:
        return None
    premarket_price = float(premarket.iloc[-1]["close"])

    btc_start = _last_at_or_before(btc, prior_ts)
    btc_end = _last_at_or_before(btc, freeze)
    if btc_start is None or btc_end is None or btc_start <= 0 or prior_close <= 0:
        return None

    open_start = _utc(session_date, time(9, 30))
    confirmation_end = _utc(session_date, time(9, 40))
    decision = _utc(session_date, time(9, 55))
    forward_30 = _utc(session_date, time(10, 25))
    forward_60 = _utc(session_date, time(10, 55))

    open_price = _first_at_or_after(equity[equity.index <= confirmation_end], open_start)
    confirmation_price = _last_at_or_before(equity[equity.index >= open_start], confirmation_end)
    decision_price = _last_at_or_before(equity[equity.index >= confirmation_end], decision)
    price_30 = _last_at_or_before(equity[equity.index >= decision], forward_30)
    price_60 = _last_at_or_before(equity[equity.index >= decision], forward_60)

    btc_return = btc_end / btc_start - 1.0
    equity_premarket_return = premarket_price / prior_close - 1.0

    return {
        "session_date": session_date,
        "btc_return": btc_return,
        "prior_close": prior_close,
        "premarket_price": premarket_price,
        "equity_premarket_return": equity_premarket_return,
        "open_10m_return": None
        if open_price is None or confirmation_price is None or open_price <= 0
        else confirmation_price / open_price - 1.0,
        "forward_30m_return": None
        if decision_price is None or price_30 is None or decision_price <= 0
        else price_30 / decision_price - 1.0,
        "forward_60m_return": None
        if decision_price is None or price_60 is None or decision_price <= 0
        else price_60 / decision_price - 1.0,
    }


def build_episode_frame(
    btc: pd.DataFrame,
    equity: pd.DataFrame,
    *,
    sessions: Iterable[date],
    beta_lookback: int = 20,
) -> pd.DataFrame:
    if beta_lookback <= 0:
        raise ValueError("beta_lookback must be positive")
    if not isinstance(btc.index, pd.DatetimeIndex) or btc.index.tz is None:
        raise ValueError("btc bars require a timezone-aware DatetimeIndex")
    if not isinstance(equity.index, pd.DatetimeIndex) or equity.index.tz is None:
        raise ValueError("equity bars require a timezone-aware DatetimeIndex")

    raw_rows = [row for day in sessions if (row := _session_raw_row(btc, equity, day)) is not None]
    frame = pd.DataFrame(raw_rows)
    if frame.empty:
        return frame
    frame = frame.sort_values("session_date").reset_index(drop=True)

    betas: list[float | None] = []
    expected: list[float | None] = []
    residuals: list[float | None] = []
    training_starts: list[date | None] = []
    training_ends: list[date | None] = []

    for index, row in frame.iterrows():
        prior = frame.iloc[max(0, index - beta_lookback) : index]
        beta = rolling_beta(
            prior["btc_return"].to_numpy(dtype=float),
            prior["equity_premarket_return"].to_numpy(dtype=float),
        )
        betas.append(beta)
        training_starts.append(None if prior.empty else prior.iloc[0]["session_date"])
        training_ends.append(None if prior.empty else prior.iloc[-1]["session_date"])
        if beta is None:
            expected.append(None)
            residuals.append(None)
        else:
            expected_return = beta * float(row["btc_return"])
            expected.append(expected_return)
            residuals.append(float(row["equity_premarket_return"]) - expected_return)

    frame["beta"] = betas
    frame["expected_return"] = expected
    frame["residual"] = residuals
    frame["training_start"] = training_starts
    frame["training_end"] = training_ends
    return frame
