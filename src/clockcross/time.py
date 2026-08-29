from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from clockcross.domain import MarketSession

ET = ZoneInfo("America/New_York")


def _at(session_date: date, wall_time: time) -> datetime:
    return datetime.combine(session_date, wall_time, tzinfo=ET)


def market_session(session_date: date) -> MarketSession:
    return MarketSession(
        session_date=session_date,
        feature_freeze=_at(session_date, time(9, 10)),
        opening_start=_at(session_date, time(9, 30)),
        confirmation_end=_at(session_date, time(9, 40)),
        decision_earliest=_at(session_date, time(9, 55)),
        regular_close=_at(session_date, time(16, 0)),
    )
