from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, model_validator

from clockcross.domain import FeatureVector
from clockcross.research.residual import rolling_beta
from clockcross.scheduler import SignalEvidence

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


class MinuteHistory(Protocol):
    def fetch_crypto_minutes(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame: ...
    def fetch_stock_minutes(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame: ...


class LiveSignalPolicy(BaseModel):
    policy_id: str
    mutation_id: str
    underlying: str
    crypto_driver: str
    thesis: Literal["continuation", "reversion"]
    beta_lookback: int = Field(gt=1)
    normalization: Literal["raw", "zscore"]
    threshold: float = Field(gt=0)
    horizon: str
    feature_freeze_et: str
    confirmation_end_et: str
    decision_time_et: str

    @model_validator(mode="after")
    def enforce_approved_policy(self) -> "LiveSignalPolicy":
        if self.policy_id != "coin-continuation-beta40-raw1pct-2026-08-29":
            raise ValueError("unapproved live signal policy id")
        if self.mutation_id != "coin-options-2026-08-29":
            raise ValueError("unapproved mutation id")
        if self.underlying != "COIN" or self.crypto_driver != "BTC/USD":
            raise ValueError("ClockCross live signal is restricted to BTC/USD -> COIN")
        if self.thesis != "continuation" or self.normalization != "raw":
            raise ValueError("approved live signal policy is raw continuation only")
        if self.beta_lookback != 40 or abs(self.threshold - 0.01) > 1e-12:
            raise ValueError("approved live signal policy requires beta40 and 1% raw threshold")
        if self.feature_freeze_et != "09:25:00" or self.confirmation_end_et != "09:40:00" or self.decision_time_et != "09:55:00":
            raise ValueError("live signal timing does not match the approved mutation")
        return self


def _utc(day: date, wall: time) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(day, wall, tzinfo=ET).astimezone(UTC))


def _exact(frame: pd.DataFrame, timestamp: pd.Timestamp, column: str) -> float | None:
    if timestamp not in frame.index:
        return None
    value = frame.loc[timestamp, column]
    if isinstance(value, pd.Series):
        return None
    return float(value)


class LiveCoinSignalGateway:
    """Reconstruct the frozen beta-40 COIN residual from time-capped SIP history."""

    def __init__(
        self,
        *,
        history: MinuteHistory,
        policy: LiveSignalPolicy,
        history_days: int = 120,
        historical_mean_signed_return: float | None = None,
    ) -> None:
        if history_days < 75:
            raise ValueError("live signal history window is too short for beta40")
        self._history = history
        self._policy = policy
        self._history_days = history_days
        self._historical_mean = historical_mean_signed_return
        self._stock: pd.DataFrame | None = None
        self._past_residuals: list[float] = []
        self._last_session: date | None = None

    def _fetch(self, session_date: date) -> tuple[pd.DataFrame, pd.DataFrame]:
        start_day = session_date - timedelta(days=self._history_days)
        start = datetime.combine(start_day, time.min, tzinfo=ET).astimezone(UTC)
        end = _utc(session_date, time(9, 40)).to_pydatetime()
        btc = self._history.fetch_crypto_minutes(self._policy.crypto_driver, start, end).sort_index()
        stock = self._history.fetch_stock_minutes(self._policy.underlying, start, end).sort_index()
        btc = btc.loc[btc.index <= pd.Timestamp(end)]
        stock = stock.loc[stock.index <= pd.Timestamp(end)]
        return btc, stock

    @staticmethod
    def _regular_closes(stock: pd.DataFrame) -> dict[date, tuple[pd.Timestamp, float]]:
        if stock.empty:
            return {}
        local = stock.tz_convert(ET)
        mask = [(time(9, 30) <= ts.time() < time(16, 0)) for ts in local.index]
        regular = local.loc[mask]
        closes: dict[date, tuple[pd.Timestamp, float]] = {}
        for day, group in regular.groupby(regular.index.date):
            last_ts = group.index[-1]
            closes[day] = (last_ts.tz_convert(UTC), float(group.iloc[-1]["close"]))
        return closes

    def _raw_rows(self, btc: pd.DataFrame, stock: pd.DataFrame, through: date) -> list[dict[str, float | date]]:
        closes = self._regular_closes(stock)
        close_days = sorted(closes)
        stock_days = sorted({ts.date() for ts in stock.tz_convert(ET).index if ts.date() <= through})
        rows: list[dict[str, float | date]] = []
        for day in stock_days:
            prior_days = [candidate for candidate in close_days if candidate < day]
            if not prior_days:
                continue
            prior_day = prior_days[-1]
            prior_ts, prior_close = closes[prior_day]
            freeze = _utc(day, time(9, 25))
            coin_price = _exact(stock, freeze, "open")
            btc_end = _exact(btc, freeze, "open")
            if coin_price is None or btc_end is None or prior_close <= 0:
                continue
            btc_start_value = btc["close"].asof(prior_ts)
            if pd.isna(btc_start_value) or float(btc_start_value) <= 0:
                continue
            btc_start = float(btc_start_value)
            rows.append(
                {
                    "session_date": day,
                    "btc_return": btc_end / btc_start - 1.0,
                    "prior_close": prior_close,
                    "premarket_price": coin_price,
                    "equity_premarket_return": coin_price / prior_close - 1.0,
                }
            )
        return rows

    def collect_premarket(self, session_date: date) -> FeatureVector | None:
        btc, stock = self._fetch(session_date)
        rows = self._raw_rows(btc, stock, session_date)
        current_indices = [index for index, row in enumerate(rows) if row["session_date"] == session_date]
        if not current_indices:
            return None
        current_index = current_indices[-1]
        lookback = self._policy.beta_lookback
        if current_index < lookback:
            return None
        prior = rows[current_index - lookback : current_index]
        beta = rolling_beta(
            np.asarray([float(row["btc_return"]) for row in prior]),
            np.asarray([float(row["equity_premarket_return"]) for row in prior]),
        )
        if beta is None:
            return None
        current = rows[current_index]
        expected = beta * float(current["btc_return"])
        residual = float(current["equity_premarket_return"]) - expected

        residual_history: list[float] = []
        for index in range(lookback, current_index):
            window = rows[index - lookback : index]
            historical_beta = rolling_beta(
                np.asarray([float(row["btc_return"]) for row in window]),
                np.asarray([float(row["equity_premarket_return"]) for row in window]),
            )
            if historical_beta is None:
                continue
            row = rows[index]
            residual_history.append(
                float(row["equity_premarket_return"]) - historical_beta * float(row["btc_return"])
            )

        self._stock = stock
        self._past_residuals = residual_history
        self._last_session = session_date
        return FeatureVector(
            session_date=session_date,
            underlying="COIN",
            crypto_driver="BTC/USD",
            btc_return=float(current["btc_return"]),
            prior_close=float(current["prior_close"]),
            premarket_price=float(current["premarket_price"]),
            equity_premarket_return=float(current["equity_premarket_return"]),
            beta=beta,
            expected_return=expected,
            residual=residual,
        )

    def opening_confirmation(self, features: FeatureVector) -> FeatureVector | None:
        if self._stock is None or self._last_session != features.session_date:
            return None
        open_price = _exact(self._stock, _utc(features.session_date, time(9, 30)), "open")
        confirm_price = _exact(self._stock, _utc(features.session_date, time(9, 40)), "open")
        if open_price is None or confirm_price is None or open_price <= 0:
            return None
        return features.model_copy(
            update={"opening_10m_return": confirm_price / open_price - 1.0}
        )

    def evaluate(self, features: FeatureVector) -> SignalEvidence:
        if features.underlying != "COIN":
            return SignalEvidence(approved=False, reason="underlying_not_approved")
        residual_z: float | None = None
        if len(self._past_residuals) >= 10:
            values = np.asarray(self._past_residuals, dtype=float)
            std = float(values.std(ddof=1))
            if np.isfinite(std) and std > np.finfo(float).eps:
                residual_z = (features.residual - float(values.mean())) / std
        approved = abs(features.residual) >= self._policy.threshold
        return SignalEvidence(
            approved=approved,
            reason=(
                "coin_beta40_raw_1pct_continuation"
                if approved
                else "residual_below_frozen_threshold"
            ),
            residual_z=residual_z,
            historical_mean_signed_return=self._historical_mean,
        )
