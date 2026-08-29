from datetime import date
from decimal import Decimal

from clockcross.alpaca.options import (
    AlpacaOptionChainRestClient,
    normalize_option_chain_payload,
    parse_occ_option_symbol,
)


def test_parse_occ_option_symbol():
    parsed = parse_occ_option_symbol("COIN260911C00300000")
    assert parsed.expiration == date(2026, 9, 11)
    assert parsed.option_type == "call"
    assert parsed.strike == Decimal("300")


def test_normalize_option_chain_payload_reads_quote_and_greeks():
    payload = {
        "snapshots": {
            "COIN260911C00300000": {
                "greeks": {"delta": 0.56},
                "latestQuote": {"ap": 5.20, "bp": 5.00, "t": "2026-08-31T13:54:55Z"},
            },
            "COIN260911C00310000": {
                "greeks": {"delta": 0.36},
                "latestQuote": {"ap": 2.90, "bp": 2.70, "t": "2026-08-31T13:54:56Z"},
            },
        }
    }
    chain = normalize_option_chain_payload("COIN", payload, feed="indicative")
    assert chain.underlying == "COIN"
    assert chain.feed == "indicative"
    assert len(chain.contracts) == 2
    assert chain.contracts[0].delta == Decimal("0.56")
    assert chain.contracts[0].quote_timestamp.tzinfo is not None


def test_normalize_skips_snapshot_without_quote_but_keeps_missing_greeks():
    payload = {
        "snapshots": {
            "COIN260911C00300000": {"greeks": {"delta": 0.56}},
            "COIN260911C00310000": {
                "latestQuote": {"ap": 2.90, "bp": 2.70, "t": "2026-08-31T13:54:56Z"}
            },
        }
    }
    chain = normalize_option_chain_payload("COIN", payload, feed="indicative")
    assert [contract.symbol for contract in chain.contracts] == ["COIN260911C00310000"]
    assert chain.contracts[0].delta is None


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.headers = {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeHttp:
    def __init__(self):
        self.calls = []
        self._responses = [
            FakeResponse({
                "snapshots": {
                    "COIN260911C00300000": {
                        "greeks": {"delta": 0.56},
                        "latestQuote": {"ap": 5.2, "bp": 5.0, "t": "2026-08-31T13:54:55Z"},
                    }
                },
                "next_page_token": "next",
            }),
            FakeResponse({
                "snapshots": {
                    "COIN260911C00310000": {
                        "greeks": {"delta": 0.36},
                        "latestQuote": {"ap": 2.9, "bp": 2.7, "t": "2026-08-31T13:54:56Z"},
                    }
                },
                "next_page_token": None,
            }),
        ]

    def get(self, url, *, params, headers):
        self.calls.append((url, dict(params), dict(headers)))
        return self._responses.pop(0)


def test_rest_client_pages_and_requests_explicit_feed():
    http = FakeHttp()
    client = AlpacaOptionChainRestClient("key", "secret", http_client=http)
    chain = client.fetch_chain(
        "COIN",
        feed="indicative",
        expiration_gte=date(2026, 9, 7),
        expiration_lte=date(2026, 9, 21),
    )
    assert len(chain.contracts) == 2
    assert len(http.calls) == 2
    assert http.calls[0][0].endswith("/v1beta1/options/snapshots/COIN")
    assert http.calls[0][1]["feed"] == "indicative"
    assert http.calls[0][1]["limit"] == 1000
    assert http.calls[1][1]["page_token"] == "next"
    assert http.calls[0][2]["APCA-API-KEY-ID"] == "key"


def test_chain_client_does_not_send_contract_master_expiration_filters():
    http = FakeHttp()
    client = AlpacaOptionChainRestClient("key", "secret", http_client=http)
    client.fetch_chain(
        "COIN",
        feed="indicative",
        expiration_gte=date(2026, 9, 7),
        expiration_lte=date(2026, 9, 21),
    )
    first_params = http.calls[0][1]
    assert "expiration_date_gte" not in first_params
    assert "expiration_date_lte" not in first_params
