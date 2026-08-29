from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

_BAR_COLUMNS = ["open", "high", "low", "close", "volume"]


def _record_value(record: object, key: str) -> Any:
    if isinstance(record, Mapping):
        return record[key]
    return getattr(record, key)


def normalize_bars(records: Iterable[object]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        timestamp = _record_value(record, "timestamp")
        row = {"timestamp": timestamp}
        row.update({column: _record_value(record, column) for column in _BAR_COLUMNS})
        rows.append(row)

    if not rows:
        empty = pd.DataFrame(columns=_BAR_COLUMNS)
        empty.index = pd.DatetimeIndex([], tz="UTC", name="timestamp")
        return empty

    frame = pd.DataFrame(rows)
    timestamps = pd.to_datetime(frame.pop("timestamp"), utc=True, errors="raise")
    frame.index = pd.DatetimeIndex(timestamps, name="timestamp")
    frame = frame[_BAR_COLUMNS].apply(pd.to_numeric, errors="raise")
    frame = frame.sort_index()

    duplicate_mask = frame.index.duplicated(keep=False)
    if duplicate_mask.any():
        for timestamp, group in frame[duplicate_mask].groupby(level=0):
            first = group.iloc[0]
            if not group.eq(first).all(axis=None):
                raise ValueError(f"conflicting duplicate bar at {timestamp}")
        frame = frame[~frame.index.duplicated(keep="first")]

    return frame


class HistoricalDataGateway:
    """Normalize provider bars and optionally cache exact research inputs."""

    def __init__(
        self,
        stock_fetcher: Callable[[str, datetime, datetime], Iterable[object]],
        crypto_fetcher: Callable[[str, datetime, datetime], Iterable[object]],
        *,
        cache_root: Path | None = None,
        stock_feed: str = "iex",
        crypto_feed: str = "alpaca",
    ) -> None:
        self._stock_fetcher = stock_fetcher
        self._crypto_fetcher = crypto_fetcher
        self._cache_root = cache_root
        self._stock_feed = stock_feed
        self._crypto_feed = crypto_feed

    def fetch_stock_minutes(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        frame = normalize_bars(self._stock_fetcher(symbol, start, end))
        self._cache("stock", symbol, start, end, self._stock_feed, frame)
        return frame

    def fetch_crypto_minutes(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        frame = normalize_bars(self._crypto_fetcher(symbol, start, end))
        self._cache("crypto", symbol, start, end, self._crypto_feed, frame)
        return frame

    def _cache(
        self,
        asset_class: str,
        symbol: str,
        start: datetime,
        end: datetime,
        feed: str,
        frame: pd.DataFrame,
    ) -> None:
        if self._cache_root is None:
            return
        safe_symbol = symbol.replace("/", "-")
        directory = self._cache_root / "raw" / safe_symbol
        directory.mkdir(parents=True, exist_ok=True)
        stem = f"{asset_class}-{start:%Y%m%dT%H%M}-{end:%Y%m%dT%H%M}-{feed}"
        frame.to_csv(directory / f"{stem}.csv")
        metadata = {
            "provider": "alpaca",
            "asset_class": asset_class,
            "symbol": symbol,
            "feed": feed,
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
            "retrieved_at": datetime.now().astimezone().isoformat(),
            "row_count": int(len(frame)),
        }
        (directory / f"{stem}.json").write_text(json.dumps(metadata, indent=2, sort_keys=True))


class AlpacaRestHistoryClient:
    """Small REST client for Alpaca historical bars with explicit pagination.

    Historical consolidated SIP data older than Alpaca's recent-data restriction
    is intentionally requested for stock research so the training feed matches
    the delayed consolidated feed used by the live Basic-plan workflow.
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        *,
        base_url: str = "https://data.alpaca.markets",
        http_client: Any | None = None,
        sleep: Callable[[float], None] | None = None,
        max_retries: int = 3,
    ) -> None:
        import httpx
        import time as time_module

        self._client = http_client or httpx.Client(timeout=30.0)
        self._sleep = sleep or time_module.sleep
        self._max_retries = max_retries
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        }

    @staticmethod
    def _rfc3339(value: datetime) -> str:
        if value.tzinfo is None:
            raise ValueError("historical request timestamps must be timezone-aware")
        return value.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _map_bar(raw: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "timestamp": raw["t"],
            "open": raw["o"],
            "high": raw["h"],
            "low": raw["l"],
            "close": raw["c"],
            "volume": raw["v"],
        }

    def _fetch_pages(
        self,
        path: str,
        params: dict[str, str | int],
        *,
        symbol: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            page_params = dict(params)
            if page_token:
                page_params["page_token"] = page_token
            attempt = 0
            while True:
                response = self._client.get(
                    f"{self._base_url}{path}",
                    params=page_params,
                    headers=self._headers,
                )
                retryable = response.status_code == 429 or response.status_code >= 500
                if not retryable:
                    response.raise_for_status()
                    break
                if attempt >= self._max_retries:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after is not None else 0.25 * (2**attempt)
                except ValueError:
                    delay = 0.25 * (2**attempt)
                self._sleep(max(0.0, delay))
                attempt += 1
            payload = response.json()
            bars = payload.get("bars", {})
            if isinstance(bars, Mapping):
                symbol_rows = bars.get(symbol, [])
            else:
                symbol_rows = bars
            rows.extend(self._map_bar(row) for row in symbol_rows)
            page_token = payload.get("next_page_token")
            if not page_token:
                return rows

    def fetch_stock_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        *,
        feed: str = "sip",
        timeframe: str = "1Min",
    ) -> list[dict[str, Any]]:
        return self._fetch_pages(
            "/v2/stocks/bars",
            {
                "symbols": symbol,
                "timeframe": timeframe,
                "start": self._rfc3339(start),
                "end": self._rfc3339(end),
                "feed": feed,
                "limit": 10000,
                "sort": "asc",
            },
            symbol=symbol,
        )

    def fetch_crypto_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        *,
        timeframe: str = "1Min",
    ) -> list[dict[str, Any]]:
        return self._fetch_pages(
            "/v1beta3/crypto/us/bars",
            {
                "symbols": symbol,
                "timeframe": timeframe,
                "start": self._rfc3339(start),
                "end": self._rfc3339(end),
                "limit": 10000,
                "sort": "asc",
            },
            symbol=symbol,
        )
