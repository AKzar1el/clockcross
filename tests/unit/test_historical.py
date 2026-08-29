import json
from pathlib import Path

import pandas as pd

from clockcross.alpaca.historical import normalize_bars


def _fixture(name: str) -> list[dict[str, object]]:
    return json.loads((Path("tests/fixtures") / name).read_text())


def test_normalize_bars_returns_sorted_utc_index() -> None:
    frame = normalize_bars(_fixture("stock_bars.json"))
    assert str(frame.index.tz) == "UTC"
    assert frame.index.is_monotonic_increasing
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]


def test_normalize_bars_preserves_premarket_observation() -> None:
    frame = normalize_bars(_fixture("stock_bars.json"))
    premarket_et = frame.tz_convert("America/New_York")
    assert pd.Timestamp("2026-08-28 08:45:00", tz="America/New_York") in premarket_et.index


def test_normalize_bars_rejects_conflicting_duplicate_timestamp() -> None:
    records = _fixture("stock_bars.json")
    duplicate = dict(records[0])
    duplicate["close"] = 999.0
    records.append(duplicate)

    try:
        normalize_bars(records)
    except ValueError as exc:
        assert "conflicting duplicate" in str(exc).lower()
    else:
        raise AssertionError("expected conflicting duplicate timestamp to be rejected")
