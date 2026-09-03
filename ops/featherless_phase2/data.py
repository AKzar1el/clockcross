from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from clockcross.agent.adjudicator import AgentContext
from clockcross.alpaca.historical import AlpacaRestHistoryClient, HistoricalDataGateway
from clockcross.research.episodes import build_episode_frame

from featherless_phase2.config import (
    DIRECTIONAL_NEWS_BOUNDARY,
    EXPECTED_SELECTION_SIGNALS,
    FROZEN_RESEARCH_MEAN,
    RAW_RESIDUAL_GATE,
    SELECTION_END,
    SELECTION_START,
    utc_at,
)


def nullable_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def live_like_residual_z(frame: pd.DataFrame, session_date: date) -> float | None:
    start = session_date - timedelta(days=120)
    window = frame.loc[
        (frame["session_date"] >= start) & (frame["session_date"] <= session_date)
    ].sort_values("session_date")
    positions = np.flatnonzero(window["session_date"].to_numpy() == session_date)
    if positions.size == 0:
        return None
    current_index = int(positions[-1])
    if current_index <= 40:
        return None
    history = window.iloc[40:current_index]["residual"].dropna().to_numpy(dtype=float)
    if history.size < 10:
        return None
    std = float(history.std(ddof=1))
    if not np.isfinite(std) or std <= np.finfo(float).eps:
        return None
    residual = float(window.iloc[current_index]["residual"])
    return (residual - float(history.mean())) / std


def build_context(row: pd.Series, *, frame: pd.DataFrame) -> AgentContext:
    residual = float(row["residual"])
    return AgentContext(
        underlying="COIN",
        residual=residual,
        residual_z=live_like_residual_z(frame, row["session_date"]),
        residual_sign=1 if residual > 0.0 else -1,
        btc_return=float(row["btc_return"]),
        opening_10m_return=nullable_float(row["open_10m_return"]),
        historical_mean_signed_return=FROZEN_RESEARCH_MEAN,
        option_feed="indicative",
        available_structures=("call_debit_spread", "put_debit_spread"),
        news_summary=DIRECTIONAL_NEWS_BOUNDARY,
    )


def synthetic_contract_contexts() -> tuple[AgentContext, ...]:
    common = {
        "underlying": "COIN",
        "historical_mean_signed_return": FROZEN_RESEARCH_MEAN,
        "option_feed": "indicative",
        "available_structures": ("call_debit_spread", "put_debit_spread"),
        "news_summary": DIRECTIONAL_NEWS_BOUNDARY,
    }
    return (
        AgentContext(
            **common,
            residual=0.0125,
            residual_z=1.7,
            residual_sign=1,
            btc_return=0.018,
            opening_10m_return=0.006,
        ),
        AgentContext(
            **common,
            residual=0.0132,
            residual_z=1.9,
            residual_sign=1,
            btc_return=0.015,
            opening_10m_return=-0.004,
        ),
        AgentContext(
            **common,
            residual=-0.0141,
            residual_z=-2.0,
            residual_sign=-1,
            btc_return=-0.020,
            opening_10m_return=-0.008,
        ),
    )


def _gateway(alpaca_key: str, alpaca_secret: str) -> HistoricalDataGateway:
    rest = AlpacaRestHistoryClient(alpaca_key, alpaca_secret)
    return HistoricalDataGateway(
        lambda symbol, start_at, end_at: rest.fetch_stock_bars(
            symbol, start_at, end_at, feed="sip"
        ),
        lambda symbol, start_at, end_at: rest.fetch_crypto_bars(
            symbol, start_at, end_at
        ),
        stock_feed="sip",
    )


def build_selection_frame(
    alpaca_key: str,
    alpaca_secret: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    history = _gateway(alpaca_key, alpaca_secret)
    start = utc_at(date(2025, 12, 1), 0, 0)
    end = utc_at(date(2026, 9, 1), 12, 0)
    stock = history.fetch_stock_minutes("COIN", start, end)
    btc = history.fetch_crypto_minutes("BTC/USD", start, end)
    sessions = [stamp.date() for stamp in pd.bdate_range("2025-12-02", "2026-08-31")]
    frame = build_episode_frame(btc, stock, sessions=sessions, beta_lookback=40)
    if frame.empty:
        raise RuntimeError("historical episode frame is empty")
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.date
    complete = frame.dropna(subset=["residual", "forward_60m_return"]).copy()
    selection = complete.loc[
        (complete["session_date"] >= SELECTION_START)
        & (complete["session_date"] <= SELECTION_END)
        & (complete["training_count"].astype(int) >= 40)
        & (complete["residual"].astype(float).abs() >= RAW_RESIDUAL_GATE)
    ].sort_values("session_date")
    if len(selection) != EXPECTED_SELECTION_SIGNALS:
        raise RuntimeError(
            f"historical anchor mismatch: expected {EXPECTED_SELECTION_SIGNALS} "
            f"pre-holdout signals, got {len(selection)}"
        )
    return frame, selection


def build_holdout_frame(
    alpaca_key: str,
    alpaca_secret: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    history = _gateway(alpaca_key, alpaca_secret)
    start = utc_at(date(2025, 12, 1), 0, 0)
    end = utc_at(date(2026, 9, 3), 12, 0)
    stock = history.fetch_stock_minutes("COIN", start, end)
    btc = history.fetch_crypto_minutes("BTC/USD", start, end)
    sessions = [stamp.date() for stamp in pd.bdate_range("2025-12-02", "2026-09-03")]
    frame = build_episode_frame(btc, stock, sessions=sessions, beta_lookback=40)
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.date
    complete = frame.dropna(subset=["residual", "forward_60m_return"]).copy()
    for anchor_date, expected_residual in (
        (date(2026, 9, 1), -0.01711816),
        (date(2026, 9, 3), 0.01147695),
    ):
        rows = complete.loc[complete["session_date"] == anchor_date]
        if rows.empty:
            raise RuntimeError(f"missing holdout anchor: {anchor_date}")
        observed = float(rows.iloc[-1]["residual"])
        if abs(observed - expected_residual) > 5e-5:
            raise RuntimeError(
                f"holdout residual anchor drift on {anchor_date}: {observed}"
            )
    return frame, complete
