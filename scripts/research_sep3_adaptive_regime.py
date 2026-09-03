from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from clockcross.agent.adjudicator import Adjudicator, AgentContext
from clockcross.alpaca.historical import AlpacaRestHistoryClient, HistoricalDataGateway
from clockcross.config import Settings
from clockcross.domain import AgentAction
from clockcross.research.episodes import build_episode_frame

ET = ZoneInfo("America/New_York")
FROZEN_MEAN = 0.002745696957097104
SIGNAL_GATE = 0.01
START = date(2025, 10, 1)
SIX_MONTH_START = date(2026, 3, 2)
RECENT_START = date(2026, 8, 3)
END = date(2026, 9, 3)


def _utc_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _utc_end(day: date) -> datetime:
    return datetime.combine(day, time(10, 55), tzinfo=ET).astimezone(timezone.utc)


def _summary(values: list[float]) -> dict[str, float | int | None]:
    clean = np.asarray([value for value in values if math.isfinite(value)], dtype=float)
    if clean.size == 0:
        return {
            "count": 0,
            "wins": 0,
            "losses": 0,
            "hit_rate": None,
            "mean": None,
            "median": None,
            "sum": 0.0,
        }
    wins = int((clean > 0).sum())
    losses = int((clean < 0).sum())
    return {
        "count": int(clean.size),
        "wins": wins,
        "losses": losses,
        "hit_rate": wins / int(clean.size),
        "mean": float(clean.mean()),
        "median": float(np.median(clean)),
        "sum": float(clean.sum()),
    }


def _thesis_return(row: pd.Series, thesis: str) -> float:
    continuation = float(np.sign(float(row["residual"]))) * float(row["forward_60m_return"])
    return continuation if thesis == "continuation" else -continuation


def _prev_signal_actions(signals: pd.DataFrame) -> list[str | None]:
    actions: list[str | None] = []
    prior_continuation_return: float | None = None
    for _, row in signals.iterrows():
        if prior_continuation_return is None:
            actions.append(None)
        else:
            actions.append("continuation" if prior_continuation_return >= 0 else "reversion")
        prior_continuation_return = _thesis_return(row, "continuation")
    return actions


def _ewma3_actions(signals: pd.DataFrame) -> list[str | None]:
    actions: list[str | None] = []
    prior: list[float] = []
    half_life = 3.0
    for _, row in signals.iterrows():
        if len(prior) < 3:
            actions.append(None)
        else:
            ages = np.arange(len(prior) - 1, -1, -1, dtype=float)
            weights = np.power(0.5, ages / half_life)
            score = float(np.average(np.asarray(prior, dtype=float), weights=weights))
            actions.append("continuation" if score >= 0 else "reversion")
        prior.append(_thesis_return(row, "continuation"))
    return actions


def _ridge10_actions(signals: pd.DataFrame) -> tuple[list[str | None], list[float | None]]:
    actions: list[str | None] = []
    predictions: list[float | None] = []
    for index, row in signals.reset_index(drop=True).iterrows():
        prior = signals.reset_index(drop=True).iloc[max(0, index - 10) : index]
        prior = prior.dropna(subset=["residual", "open_10m_return", "forward_60m_return"])
        if len(prior) < 10:
            actions.append(None)
            predictions.append(None)
            continue
        x = prior[["residual", "open_10m_return"]].to_numpy(dtype=float)
        y = prior["forward_60m_return"].to_numpy(dtype=float)
        mean = x.mean(axis=0)
        std = x.std(axis=0, ddof=1)
        if np.any(~np.isfinite(std)) or np.any(std <= np.finfo(float).eps):
            actions.append(None)
            predictions.append(None)
            continue
        z = (x - mean) / std
        design = np.column_stack([np.ones(len(z)), z])
        penalty = np.diag([0.0, 1.0, 1.0])
        coef = np.linalg.solve(design.T @ design + penalty, design.T @ y)
        target = np.asarray([float(row["residual"]), float(row["open_10m_return"])])
        target_z = (target - mean) / std
        prediction = float(np.asarray([1.0, *target_z]) @ coef)
        predictions.append(prediction)
        if abs(prediction) <= 1e-12:
            actions.append(None)
        else:
            # Prediction is an absolute COIN return, not a residual-relative thesis.
            residual_sign = 1 if float(row["residual"]) > 0 else -1
            predicted_sign = 1 if prediction > 0 else -1
            actions.append("continuation" if predicted_sign == residual_sign else "reversion")
    return actions, predictions


def _residual_z(frame: pd.DataFrame, row_index: int) -> float | None:
    prior = frame.iloc[:row_index]["residual"].dropna().astype(float)
    if len(prior) < 10:
        return None
    std = float(prior.std(ddof=1))
    if not math.isfinite(std) or std <= np.finfo(float).eps:
        return None
    return (float(frame.iloc[row_index]["residual"]) - float(prior.mean())) / std


def _news_payload(session: requests.Session, api_key: str, secret: str, day: date) -> list[dict[str, Any]]:
    start = datetime.combine(day, time(0, 0), tzinfo=ET).astimezone(timezone.utc)
    end = datetime.combine(day, time(9, 55), tzinfo=ET).astimezone(timezone.utc)
    response = session.get(
        "https://data.alpaca.markets/v1beta1/news",
        headers={"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret},
        params={
            "symbols": "COIN",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "sort": "desc",
            "limit": 10,
            "include_content": "false",
        },
        timeout=30,
    )
    response.raise_for_status()
    items = response.json().get("news", [])
    sanitized: list[dict[str, Any]] = []
    for item in items:
        sanitized.append(
            {
                "headline": str(item.get("headline", ""))[:300],
                "summary": str(item.get("summary", ""))[:400],
                "created_at": item.get("created_at"),
                "symbols": item.get("symbols", []),
            }
        )
    return sanitized


def _ai_replay(frame: pd.DataFrame, signals: pd.DataFrame, *, api_key: str, secret: str) -> list[dict[str, Any]]:
    llm_key = os.environ["LLM_API_KEY"]
    llm_base = os.environ["LLM_BASE_URL"]
    llm_model = os.environ["LLM_MODEL"]
    adjudicator = Adjudicator(base_url=llm_base, api_key=llm_key, model=llm_model, timeout_seconds=30)
    http = requests.Session()
    index_by_date = {row["session_date"]: idx for idx, row in frame.iterrows()}
    results: list[dict[str, Any]] = []
    for _, row in signals.iterrows():
        day = row["session_date"]
        news = _news_payload(http, api_key, secret, day)
        news_summary = json.dumps(news, sort_keys=True, separators=(",", ":"))[:1600]
        decision = adjudicator.decide(
            AgentContext(
                underlying="COIN",
                residual=float(row["residual"]),
                residual_z=_residual_z(frame, index_by_date[day]),
                residual_sign=1 if float(row["residual"]) > 0 else -1,
                btc_return=float(row["btc_return"]),
                opening_10m_return=float(row["open_10m_return"]),
                historical_mean_signed_return=FROZEN_MEAN,
                option_feed="indicative",
                available_structures=("call_debit_spread", "put_debit_spread"),
                news_summary=news_summary,
            )
        )
        realized: float | None = None
        if decision.action is AgentAction.CONTINUATION:
            realized = _thesis_return(row, "continuation")
        elif decision.action is AgentAction.REVERSION:
            realized = _thesis_return(row, "reversion")
        results.append(
            {
                "session_date": day.isoformat(),
                "action": decision.action.value,
                "driver": decision.driver.value,
                "idiosyncratic_news_detected": decision.idiosyncratic_news_detected,
                "confidence": decision.confidence,
                "reason": decision.reason,
                "news_count": len(news),
                "residual": float(row["residual"]),
                "opening_10m_return": float(row["open_10m_return"]),
                "forward_60m_return": float(row["forward_60m_return"]),
                "continuation_return": _thesis_return(row, "continuation"),
                "reversion_return": _thesis_return(row, "reversion"),
                "realized_directional_return": realized,
            }
        )
    return results


def _metrics_for_actions(signals: pd.DataFrame, actions: list[str | None], start: date) -> dict[str, Any]:
    values: list[float] = []
    dates: list[str] = []
    for (_, row), action in zip(signals.iterrows(), actions, strict=True):
        if row["session_date"] < start or action is None:
            continue
        values.append(_thesis_return(row, action))
        dates.append(row["session_date"].isoformat())
    return {"summary": _summary(values), "dates": dates}


def main() -> None:
    settings = Settings()
    api_key = os.environ["ALPACA_API_KEY"]
    secret = os.environ["ALPACA_SECRET_KEY"]
    rest = AlpacaRestHistoryClient(api_key, secret, base_url=str(settings.alpaca_data_base_url))
    gateway = HistoricalDataGateway(
        stock_fetcher=lambda symbol, begin, finish: rest.fetch_stock_bars(symbol, begin, finish, feed="sip"),
        crypto_fetcher=lambda symbol, begin, finish: rest.fetch_crypto_bars(symbol, begin, finish),
        cache_root=Path("artifacts/tmp-sep3-adaptive"),
        stock_feed="sip",
    )
    btc = gateway.fetch_crypto_minutes("BTC/USD", _utc_start(START), _utc_end(END))
    coin = gateway.fetch_stock_minutes("COIN", _utc_start(START), _utc_end(END))
    sessions = [stamp.date() for stamp in pd.date_range(START, END, freq="B")]
    frame = build_episode_frame(btc, coin, sessions=sessions, beta_lookback=40)
    frame = frame.loc[
        (frame["training_count"].astype(int) >= 40)
        & frame["residual"].notna()
        & frame["open_10m_return"].notna()
        & frame["forward_60m_return"].notna()
    ].reset_index(drop=True)
    signals = frame.loc[
        (frame["session_date"] >= SIX_MONTH_START)
        & (frame["residual"].astype(float).abs() >= SIGNAL_GATE)
    ].reset_index(drop=True)

    prev_actions = _prev_signal_actions(signals)
    ewma_actions = _ewma3_actions(signals)
    ridge_actions, ridge_predictions = _ridge10_actions(signals)

    ai = _ai_replay(frame, signals, api_key=api_key, secret=secret)
    ai_values = [
        float(item["realized_directional_return"])
        for item in ai
        if item["realized_directional_return"] is not None
    ]
    ai_recent_values = [
        float(item["realized_directional_return"])
        for item in ai
        if item["realized_directional_return"] is not None
        and date.fromisoformat(item["session_date"]) >= RECENT_START
    ]
    company_vetoes = [item for item in ai if item["driver"] == "company_specific" or item["idiosyncratic_news_detected"]]

    sep3_index = next(i for i, row in signals.iterrows() if row["session_date"] == END)
    sep3_row = signals.iloc[sep3_index]
    sep3_ai = next(item for item in ai if item["session_date"] == END.isoformat())

    payload = {
        "study": "sep3_adaptive_regime_and_company_news_veto",
        "information_discipline": "all adaptive actions use prior completed signal outcomes only; historical AI news is capped at 09:55 ET; no order client is instantiated",
        "signal_count": int(len(signals)),
        "windows": {
            "six_month_start": SIX_MONTH_START.isoformat(),
            "recent_start": RECENT_START.isoformat(),
            "end": END.isoformat(),
        },
        "benchmarks": {
            "continuation_six_month": _summary([_thesis_return(row, "continuation") for _, row in signals.iterrows()]),
            "reversion_six_month": _summary([_thesis_return(row, "reversion") for _, row in signals.iterrows()]),
            "current_ai_replay_six_month": _summary(ai_values),
            "current_ai_replay_recent": _summary(ai_recent_values),
        },
        "adaptive": {
            "previous_signal": {
                "six_month": _metrics_for_actions(signals, prev_actions, SIX_MONTH_START),
                "recent": _metrics_for_actions(signals, prev_actions, RECENT_START),
            },
            "ewma_half_life_3_signals": {
                "six_month": _metrics_for_actions(signals, ewma_actions, SIX_MONTH_START),
                "recent": _metrics_for_actions(signals, ewma_actions, RECENT_START),
            },
            "rolling_ridge_10_signals": {
                "features": ["residual", "open_10m_return"],
                "ridge_lambda": 1.0,
                "six_month": _metrics_for_actions(signals, ridge_actions, SIX_MONTH_START),
                "recent": _metrics_for_actions(signals, ridge_actions, RECENT_START),
            },
        },
        "company_specific_vetoes": company_vetoes,
        "company_specific_veto_hypotheticals": {
            "count": len(company_vetoes),
            "continuation": _summary([float(item["continuation_return"]) for item in company_vetoes]),
            "reversion": _summary([float(item["reversion_return"]) for item in company_vetoes]),
            "absolute_forward": _summary([abs(float(item["forward_60m_return"])) for item in company_vetoes]),
        },
        "sep3": {
            "residual": float(sep3_row["residual"]),
            "opening_10m_return": float(sep3_row["open_10m_return"]),
            "forward_60m_return": float(sep3_row["forward_60m_return"]),
            "continuation_return": _thesis_return(sep3_row, "continuation"),
            "reversion_return": _thesis_return(sep3_row, "reversion"),
            "current_ai": sep3_ai,
            "previous_signal_action": prev_actions[sep3_index],
            "previous_signal_return": None if prev_actions[sep3_index] is None else _thesis_return(sep3_row, prev_actions[sep3_index]),
            "ewma3_action": ewma_actions[sep3_index],
            "ewma3_return": None if ewma_actions[sep3_index] is None else _thesis_return(sep3_row, ewma_actions[sep3_index]),
            "ridge10_action": ridge_actions[sep3_index],
            "ridge10_prediction": ridge_predictions[sep3_index],
            "ridge10_return": None if ridge_actions[sep3_index] is None else _thesis_return(sep3_row, ridge_actions[sep3_index]),
        },
        "ai_signal_rows": ai,
    }
    out = Path("artifacts/tmp-sep3-adaptive/result.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
