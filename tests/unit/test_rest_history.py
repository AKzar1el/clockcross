from datetime import datetime, timezone

import httpx

from clockcross.alpaca.historical import AlpacaRestHistoryClient


def test_stock_bars_use_sip_and_follow_pagination() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        params = dict(request.url.params)
        if "page_token" not in params:
            return httpx.Response(
                200,
                json={
                    "bars": {
                        "COIN": [
                            {
                                "t": "2026-08-28T13:10:00Z",
                                "o": 1,
                                "h": 2,
                                "l": 1,
                                "c": 2,
                                "v": 10,
                            }
                        ]
                    },
                    "next_page_token": "next",
                },
            )
        return httpx.Response(
            200,
            json={
                "bars": {
                    "COIN": [
                        {
                            "t": "2026-08-28T13:11:00Z",
                            "o": 2,
                            "h": 3,
                            "l": 2,
                            "c": 3,
                            "v": 11,
                        }
                    ]
                },
                "next_page_token": None,
            },
        )

    client = AlpacaRestHistoryClient(
        api_key="key",
        secret_key="secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    rows = client.fetch_stock_bars(
        "COIN",
        datetime(2026, 8, 28, tzinfo=timezone.utc),
        datetime(2026, 8, 29, tzinfo=timezone.utc),
        feed="sip",
    )

    assert len(rows) == 2
    assert rows[0]["timestamp"] == "2026-08-28T13:10:00Z"
    assert calls[0].url.path == "/v2/stocks/bars"
    assert calls[0].url.params["feed"] == "sip"
    assert calls[1].url.params["page_token"] == "next"
    assert calls[0].headers["APCA-API-KEY-ID"] == "key"


def test_crypto_bars_use_current_v1beta3_us_endpoint() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "bars": {
                    "BTC/USD": [
                        {
                            "t": "2026-08-28T13:10:00Z",
                            "o": 10,
                            "h": 11,
                            "l": 9,
                            "c": 10.5,
                            "v": 1,
                        }
                    ]
                },
                "next_page_token": None,
            },
        )

    client = AlpacaRestHistoryClient(
        api_key="key",
        secret_key="secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    rows = client.fetch_crypto_bars(
        "BTC/USD",
        datetime(2026, 8, 28, tzinfo=timezone.utc),
        datetime(2026, 8, 29, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert seen[0].url.path == "/v1beta3/crypto/us/bars"
    assert seen[0].url.params["symbols"] == "BTC/USD"


def test_historical_client_retries_rate_limit_without_dropping_page_state() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0"},
                json={"message": "rate limit"},
            )
        return httpx.Response(
            200,
            json={
                "bars": {
                    "COIN": [
                        {
                            "t": "2026-08-28T13:25:00Z",
                            "o": 1,
                            "h": 2,
                            "l": 1,
                            "c": 2,
                            "v": 10,
                        }
                    ]
                },
                "next_page_token": None,
            },
        )

    client = AlpacaRestHistoryClient(
        api_key="key",
        secret_key="secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=sleeps.append,
        max_retries=2,
    )
    rows = client.fetch_stock_bars(
        "COIN",
        datetime(2026, 8, 28, tzinfo=timezone.utc),
        datetime(2026, 8, 29, tzinfo=timezone.utc),
    )

    assert attempts == 2
    assert sleeps == [0.0]
    assert len(rows) == 1
