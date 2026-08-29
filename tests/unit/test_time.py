from datetime import date

from clockcross.time import market_session


def test_market_session_freeze_and_decision_boundaries() -> None:
    session = market_session(date(2026, 8, 31))
    assert session.feature_freeze.isoformat().endswith("09:10:00-04:00")
    assert session.opening_start.isoformat().endswith("09:30:00-04:00")
    assert session.confirmation_end.isoformat().endswith("09:40:00-04:00")
    assert session.decision_earliest.isoformat().endswith("09:55:00-04:00")
